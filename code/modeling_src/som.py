"""Kohonen Self-Organizing Map (SOM) on normalised embeddings.

A SOM projects high-dimensional embeddings onto a 2D toroidal grid (here a
square grid) so that similar calls land near each other.  We accumulate each
call's Best-Matching Unit (BMU) cell to build a density/topographic map.

Training is a batch update (GPU-accelerated):

    for each epoch:
        for each mini-batch X:
            S = X @ W.T                     # (b, grid*grid) cosine similarities
            bmu = argmax(S, dim=1)
            neighborhood = exp(-dist2(bmu_cell, all_cells) / (2 sigma^2))
            W += lr * neighborhood * (X - W)

Weights stay on the unit sphere (renormalised) so similarity stays cosine-based.
"""
from __future__ import annotations

import numpy as np
import torch
from pathlib import Path

import joblib


class KohonenSOM:
    def __init__(self, grid: int = 28, dim: int = 1024, epochs: int = 25,
                 lr0: float = 0.4, sigma0: float = 6.0, seed: int = 42,
                 batch_size: int = 1024, device: str | None = None):
        self.grid = grid
        self.dim = dim
        self.epochs = epochs
        self.lr0 = lr0
        self.sigma0 = sigma0
        self.seed = seed
        self.batch_size = batch_size
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.weights_: torch.Tensor | None = None

    # --------------------------------------------------------------- training
    def fit(self, X: np.ndarray, verbose: bool = True) -> "KohonenSOM":
        torch.manual_seed(self.seed)
        rng = np.random.RandomState(self.seed)
        dev = self.device
        grid = self.grid
        n = len(X)
        W = torch.randn(grid * grid, self.dim, device=dev)
        W = W / W.norm(dim=1, keepdim=True).clamp_min(1e-12)

        # grid coordinates for each cell (row, col)
        coords = torch.tensor(
            [[r, c] for r in range(grid) for c in range(grid)], dtype=torch.float32, device=dev)
        # precompute squared grid distances between all cells (grid*grid, grid*grid)
        d2 = ((coords[:, None, :] - coords[None, :, :]) ** 2).sum(-1)

        Xt = torch.tensor(X, dtype=torch.float32, device=dev)
        Xt = Xt / Xt.norm(dim=1, keepdim=True).clamp_min(1e-12)

        n_steps = max(1, n // self.batch_size)
        for epoch in range(self.epochs):
            t = epoch / self.epochs
            lr = self.lr0 * (1.0 - t)
            sigma = max(1.0, self.sigma0 * (1.0 - t))
            perm = rng.permutation(n)
            for s in range(0, n, self.batch_size):
                idx = perm[s:s + self.batch_size]
                Xb = Xt[idx]
                S = Xb @ W.t()                       # (b, grid*grid)
                bmu = S.argmax(dim=1)
                neigh = torch.exp(-d2[bmu] / (2.0 * sigma * sigma))  # (b, grid*grid)
                neigh = torch.clamp(neigh, min=0.0, max=1.0)
                # vectorised batch update:
                #   W += lr * sum_b h(cell, bmu_b) * (x_b - w_bmu_b)
                delta = Xb - W[bmu]                  # (b, dim)
                W += lr * (neigh.t() @ delta)        # (cells, dim) @ ... -> (cells, dim)
            W = W / W.norm(dim=1, keepdim=True).clamp_min(1e-12)
            if verbose:
                print(f"  som epoch {epoch + 1:02d}/{self.epochs}  lr={lr:.3f}  sigma={sigma:.2f}")

        self.weights_ = W
        self.coords_ = coords.cpu().numpy()
        self.d2_ = d2.cpu().numpy()
        return self

    # ------------------------------------------------------------ BMU / density
    def bmu_batch(self, X: np.ndarray, batch_size: int = 4096) -> np.ndarray:
        """Return the BMU cell id (0..grid^2-1) for each sample."""
        dev = self.device
        W = self.weights_.to(dev)
        out = np.zeros(len(X), dtype=np.int64)
        for s in range(0, len(X), batch_size):
            Xb = torch.tensor(X[s:s + batch_size], dtype=torch.float32, device=dev)
            Xb = Xb / Xb.norm(dim=1, keepdim=True).clamp_min(1e-12)
            out[s:s + batch_size] = (Xb @ W.t()).argmax(dim=1).cpu().numpy()
        return out

    def accumulate_density(self, X: np.ndarray, batch_size: int = 4096) -> np.ndarray:
        """Count how many calls map to each cell -> (grid, grid) density matrix."""
        cells = self.bmu_batch(X, batch_size=batch_size)
        dens = np.zeros(self.grid * self.grid, dtype=np.int64)
        np.add.at(dens, cells, 1)
        return dens.reshape(self.grid, self.grid)

    # --------------------------------------------------------------- artifacts
    def save(self, path: Path | str) -> None:
        joblib.dump({
            "grid": self.grid, "dim": self.dim, "epochs": self.epochs,
            "lr0": self.lr0, "sigma0": self.sigma0, "seed": self.seed,
            "weights": self.weights_.cpu().numpy(),
            "coords": self.coords_, "d2": self.d2_,
        }, path)

    @classmethod
    def load(cls, path: Path | str) -> "KohonenSOM":
        d = joblib.load(path)
        obj = cls(d["grid"], d["dim"], d["epochs"], d["lr0"], d["sigma0"], seed=d["seed"])
        obj.weights_ = torch.tensor(d["weights"], dtype=torch.float32)
        obj.coords_ = d["coords"]
        obj.d2_ = d["d2"]
        return obj