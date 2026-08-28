from __future__ import annotations

import numpy as np


def _edge_matrix(edges: tuple[tuple[int, int], ...], nodes: int) -> np.ndarray:
    matrix = np.zeros((nodes, nodes), dtype=np.float32)
    for source, target in edges:
        matrix[target, source] = 1
    return matrix


def _normalize_digraph(matrix: np.ndarray) -> np.ndarray:
    degree = np.sum(matrix, axis=0)
    inverse = np.zeros((matrix.shape[1], matrix.shape[1]), dtype=np.float32)
    for index, value in enumerate(degree):
        if value > 0:
            inverse[index, index] = value ** -1
    return matrix @ inverse


class CocoGraph:
    """The exact 17-node COCO spatial graph used by STGCN-Extend."""

    inward = (
        (15, 13), (13, 11), (16, 14), (14, 12), (11, 5), (12, 6),
        (9, 7), (7, 5), (10, 8), (8, 6), (5, 0), (6, 0),
        (1, 0), (3, 1), (2, 0), (4, 2),
    )

    def __init__(self) -> None:
        nodes = 17
        identity = _edge_matrix(tuple((index, index) for index in range(nodes)), nodes)
        inward = _normalize_digraph(_edge_matrix(self.inward, nodes))
        outward = _normalize_digraph(
            _edge_matrix(tuple((target, source) for source, target in self.inward), nodes)
        )
        self.A = np.stack((identity, inward, outward))
