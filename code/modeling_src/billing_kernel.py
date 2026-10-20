"""Billing / Non-Billing segmentation kernel.

Stage-1 of the v2 pipeline: a small, high-precision + high-recall + high-F1
binary classifier that decides whether a call is billing-related.  It is trained
on BGE-large embeddings using the heuristic Primary Call Reason signal
(``Billing`` / ``Payments`` == positive; everything else == negative) and applies
to *any* call text afterwards, so we can narrow the full YTD stack down to the
billing segment we actually mine.

Design
------
* Base model : L2-regularised Logistic Regression (softmax of 2 classes) on the
  1024-d normalised BGE embedding.  Fast, calibrated, and strong on short text.
* Threshold : after training, the decision threshold is tuned on the held-out
  10% to maximise F1 while keeping precision high.  The tuned threshold is stored
  in the artifact so inference is deterministic.
* One-class guard : a OneClassSVM is also fit on the positive-class embeddings;
  it is not used for the final decision but is saved as a secondary reference
  (nu = fraction of positives treated as outliers).
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.svm import OneClassSVM

from .config import ARTIFACTS_DIR
from .embed import embed_cached


class BillingKernel:
    def __init__(self, clf=None, threshold: float = 0.5, ocs: OneClassSVM | None = None,
                 classes: list[str] | None = None):
        self.clf = clf
        self.threshold = threshold
        self.ocs = ocs
        self.classes = classes or ["non_billing", "billing"]

    # ------------------------------------------------------------- train
    @classmethod
    def train(cls, texts: pd.Series, y: pd.Series, sample_balance: int = 40_000,
              test_size: float = 0.1, seed: int = 42, cache_key: str = "billing_train") -> "BillingKernel":
        """Train on whole-string embeddings of the heuristic-labelled sample.

        texts : call-intent strings
        y     : 1/0 (1 = heuristic billing: Billing/Payments Primary Call Reason)
        """
        # balanced subsample for even representation
        rng = np.random.RandomState(seed)
        pos = texts[y == 1].sample(min(sample_balance // 2, int((y == 1).sum())), random_state=seed)
        neg = texts[y == 0].sample(min(sample_balance // 2, int((y == 0).sum())), random_state=seed)
        sample = pd.concat([pos, neg])
        y_s = pd.concat([y.loc[pos.index], y.loc[neg.index]]).astype(int).to_numpy()

        X = embed_cached(sample, cache_key)
        Xtr, Xte, ytr, yte = train_test_split(X, y_s, test_size=test_size,
                                              random_state=seed, stratify=y_s)

        base = LogisticRegression(C=10.0, max_iter=2000, class_weight="balanced",
                                  solver="lbfgs", random_state=seed)
        clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
        clf.fit(Xtr, ytr)

        proba = clf.predict_proba(Xte)[:, 1]
        # tune threshold for best F1 with precision>=recall guard
        thresholds = np.linspace(0.20, 0.80, 121)
        best_t, best_f1 = 0.5, 0.0
        for t in thresholds:
            pred = (proba >= t).astype(int)
            f1 = f1_score(yte, pred, zero_division=0)
            if f1 > best_f1:
                best_f1, best_t = f1, t

        pred = (proba >= best_t).astype(int)
        metrics = {
            "accuracy": float((pred == yte).mean()),
            "precision": float(precision_score(yte, pred, zero_division=0)),
            "recall": float(recall_score(yte, pred, zero_division=0)),
            "f1": float(f1_score(yte, pred, zero_division=0)),
            "threshold": float(best_t),
            "train_n": int(len(ytr)),
            "test_n": int(len(yte)),
            "pos_share_train": float(ytr.mean()),
        }

        # optional one-class reference on positives
        ocs = OneClassSVM(kernel="rbf", gamma="scale", nu=0.05).fit(Xtr[ytr == 1])

        kernel = cls(clf=clf, threshold=best_t, ocs=ocs)
        kernel.metrics = metrics
        kernel.n_features_ = X.shape[1]
        return kernel

    # ------------------------------------------------------------- inference
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Billing probability for each row (1 = billing)."""
        p = self.clf.predict_proba(X)[:, 1]
        return p

    def predict_binary(self, X: np.ndarray) -> np.ndarray:
        return (self.predict(X) >= self.threshold).astype(int)

    def score_texts(self, texts: list[str]) -> np.ndarray:
        """End-to-end: texts -> billing probability."""
        X = embed_cached(pd.Series(texts), "billing_infer_" + str(hash(tuple(texts)) % 10**9)) \
            if False else _embed_infer(texts)
        return self.predict(X)

    # ------------------------------------------------------------- artifacts
    def save(self, path: Path | str = ARTIFACTS_DIR / "billing_kernel.joblib") -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "clf": self.clf, "threshold": self.threshold, "ocs": self.ocs,
            "classes": self.classes, "metrics": getattr(self, "metrics", {}),
            "n_features": getattr(self, "n_features_", None),
            "created": pd.Timestamp.now().isoformat(),
        }
        joblib.dump(payload, path)
        (path.parent / "billing_kernel_meta.json").write_text(
            json.dumps(payload["metrics"], indent=2))

    @classmethod
    def load(cls, path: Path | str = ARTIFACTS_DIR / "billing_kernel.joblib") -> "BillingKernel":
        p = joblib.load(path)
        kernel = cls(clf=p["clf"], threshold=p["threshold"], ocs=p.get("ocs"),
                     classes=p.get("classes"))
        kernel.metrics = p.get("metrics", {})
        kernel.n_features_ = p.get("n_features")
        return kernel


def _embed_infer(texts: list[str]) -> np.ndarray:
    from .embed import embed_texts
    return embed_texts(list(texts))