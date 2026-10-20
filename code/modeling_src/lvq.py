"""Generalised Learning Vector Quantization (GLVQ) on normalised embeddings.

GLVQ (Sato & Yamada, 1996) learns a set of prototype vectors — one per taxonomy
subcategory — by gradient descent on a cost function that rewards each sample
being closer to its own-class prototype than to any other-class prototype.

For unit vectors (normalised embeddings) the squared-Euclidean distance
``d = ||x - w||^2 = 2 - 2 cos(x, w)`` is monotonic with cosine similarity, so the
model maximises cosine separation between subcategory prototypes while covering
the data (every sample is labelled by its cluster -> taxonomy mapping).

Update rule (batch-vectorised over mini-batches):
    mu    = (d_c - d_j) / (d_c + d_j)          # negative => correct side
    w_c  -= alpha * phi'(mu) * 2 d_j/(d_c+d_j)^2 * (x - w_c)
    w_j  += alpha * phi'(mu) * 2 d_c/(d_c+d_j)^2 * (x - w_j)

Prototypes are renormalised after every step to stay on the unit sphere.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np


def _phi_prime(mu: np.ndarray, scale: float = 2.0) -> np.ndarray:
    """Derivative of the logistic phi used by GLVQ (sigmoid slope at 0 = scale/4)."""
    return scale / (1.0 + np.exp(-scale * mu)) * (1.0 - 1.0 / (1.0 + np.exp(-scale * mu)))


class GLVQ:
    """Prototype-based classifier maximising inter-class separation.

    Parameters
    ----------
    n_prototypes : int
        Number of prototypes (== number of subcategory labels).
    dim : int
        Embedding dimension.
    epochs : int
        Full passes over the training set.
    alpha0 : float
        Initial learning rate (linear decay to ~0 over training).
    batch_size : int
        Mini-batch size for the vectorised update.
    seed : int
        Random seed.
    """

    def __init__(self, n_prototypes: int, dim: int, epochs: int = 20,
                 alpha0: float = 0.3, batch_size: int = 512, seed: int = 42):
        self.n_prototypes = n_prototypes
        self.dim = dim
        self.epochs = epochs
        self.alpha0 = alpha0
        self.batch_size = batch_size
        self.seed = seed
        self.prototypes_: np.ndarray | None = None
        self.prototype_labels_: np.ndarray | None = None

    # ------------------------------------------------------------------ fit
    def fit(self, X: np.ndarray, y: np.ndarray,
            prototypes0: np.ndarray, prototype_labels: np.ndarray,
            verbose: bool = True) -> "GLVQ":
        """Train GLVQ.

        X : (n, dim) normalised embeddings
        y : (n,) integer labels, one per training sample (cluster->subcategory id)
        prototypes0 : (n_prototypes, dim) seed prototypes (embedded taxonomy seeds)
        prototype_labels : (n_prototypes,) int labels of each prototype
        """
        assert X.shape[1] == self.dim
        assert prototypes0.shape == (self.n_prototypes, self.dim)
        rng = np.random.RandomState(self.seed)
        self.prototypes_ = prototypes0.copy()
        self.prototype_labels_ = prototype_labels.astype(int)
        uniq = np.unique(self.prototype_labels_)
        assert set(np.unique(y)) <= set(uniq), "training labels must be a subset of prototype labels"

        n = len(X)
        for epoch in range(self.epochs):
            alpha = self.alpha0 * (1.0 - epoch / self.epochs)
            # shuffle
            perm = rng.permutation(n)
            for start in range(0, n, self.batch_size):
                idx = perm[start:start + self.batch_size]
                self._update_batch(X[idx], y[idx], alpha)
            if verbose:
                acc = self.score(X, y)
                print(f"  epoch {epoch + 1:02d}/{self.epochs}  alpha={alpha:.3f}  train-acc={acc:.4f}")
        return self

    def _update_batch(self, Xb: np.ndarray, yb: np.ndarray, alpha: float) -> None:
        W = self.prototypes_
        L = self.prototype_labels_
        S = Xb @ W.T                      # cosine similarities (n, m)
        new_W = W.copy()
        for label in np.unique(self.prototype_labels_):
            rows = np.where(yb == label)[0]
            if len(rows) == 0:
                continue
            c_mask = L == label
            j_mask = ~c_mask
            c_pos = np.where(c_mask)[0]           # prototype indices of class
            j_pos = np.where(j_mask)[0]           # prototype indices of non-class
            Sc = S[rows][:, c_mask]
            Sj = S[rows][:, j_mask]
            c_sim = Sc.max(axis=1)
            j_sim = Sj.max(axis=1)
            c_idx = c_pos[Sc.argmax(axis=1)]
            j_idx = j_pos[Sj.argmax(axis=1)]
            # distances from similarities (unit vectors)
            dc = 2.0 - 2.0 * c_sim
            dj = 2.0 - 2.0 * j_sim
            denom = dc + dj + 1e-12
            mu = (dc - dj) / denom
            psi = _phi_prime(mu)
            x = Xb[rows]
            wc = W[c_idx]                 # nearest correct prototypes
            wj = W[j_idx]                 # nearest incorrect prototypes
            factor_c = psi * (4.0 * dj / denom ** 2)
            factor_j = psi * (4.0 * dc / denom ** 2)
            # w+ moves toward x (np.add), w- moves away from x (np.subtract)
            np.add.at(new_W, c_idx, alpha * factor_c[:, None] * (x - wc))
            np.subtract.at(new_W, j_idx, alpha * factor_j[:, None] * (x - wj))
        # renormalise and commit
        norms = np.linalg.norm(new_W, axis=1, keepdims=True)
        new_W = new_W / np.clip(norms, 1e-12, None)
        self.prototypes_ = new_W

    # -------------------------------------------------------------- predict
    def decision_scores(self, X: np.ndarray) -> np.ndarray:
        """Cosine similarity of each sample to every prototype (n, m)."""
        return X @ self.prototypes_.T

    def predict(self, X: np.ndarray) -> np.ndarray:
        sim = self.decision_scores(X)
        return self.prototype_labels_[sim.argmax(axis=1)]

    def score(self, X: np.ndarray, y: np.ndarray) -> float:
        if len(X) == 0:
            return 0.0
        return float(np.mean(self.predict(X) == y))

    def predict_proba_topk(self, X: np.ndarray, k: int = 3) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Top-k prototype indices + softmax-normalised confidence.

        Returns (top_idx (n,k), top_sim (n,k), top_prob (n,k)).
        Confidence is a temperature-softmax over the k selected similarities.
        """
        sim = self.decision_scores(X)
        top = np.argsort(-sim, axis=1)[:, :k]
        top_sim = np.take_along_axis(sim, top, axis=1)
        # temperature softmax over the selected k
        t = 0.1
        e = np.exp(top_sim / t)
        prob = e / e.sum(axis=1, keepdims=True)
        return top, top_sim, prob

    # ------------------------------------------------------------- artifacts
    def save(self, path: Path | str) -> None:
        joblib.dump({
            "n_prototypes": self.n_prototypes,
            "dim": self.dim,
            "epochs": self.epochs,
            "alpha0": self.alpha0,
            "seed": self.seed,
            "prototypes_": self.prototypes_,
            "prototype_labels_": self.prototype_labels_,
        }, path)

    @classmethod
    def load(cls, path: Path | str) -> "GLVQ":
        d = joblib.load(path)
        obj = cls(d["n_prototypes"], d["dim"], d["epochs"], d["alpha0"], seed=d["seed"])
        obj.prototypes_ = d["prototypes_"]
        obj.prototype_labels_ = d["prototype_labels_"]
        return obj