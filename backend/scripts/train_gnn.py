#!/usr/bin/env python3
"""Train physics-informed GNN on synthetic supervision from graph base_risk."""
import asyncio
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.graph_seed import seed_graph_if_empty
from app.db.neo4j import db
from app.models.gnn import TemporalGraphNetwork, compute_physics_loss
from app.services.trainer import train_physics_informed_gnn


async def build_training_batch():
    await db.connect()
    await seed_graph_if_empty()
    geo_nodes, sources, targets, edge_meta = await db.get_dynamic_topology()
    n = len(geo_nodes)
    if n == 0 or not sources:
        raise RuntimeError("No graph data for training.")

    import random

    features = torch.tensor(
        [[random.uniform(0.1, 0.5) for _ in range(3)] for _ in range(n)],
        dtype=torch.float,
    )
    adj = torch.eye(n)
    for s, t in zip(sources, targets):
        adj[s][t] = 1.0
        adj[t][s] = 1.0
    edge_index = torch.stack(
        [torch.tensor(sources, dtype=torch.long), torch.tensor(targets, dtype=torch.long)],
        dim=0,
    )
    y = torch.tensor(
        [[float(m.get("base_risk", 0.5))] for m in edge_meta[: len(sources)]],
        dtype=torch.float,
    )

    class Batch:
        pass

    Batch.x = features
    Batch.adj = adj
    Batch.edge_index = edge_index
    Batch.y = y
    Batch.metrics = edge_meta

    return [Batch()]


async def main():
    batches = await build_training_batch()

    class Loader:
        def __iter__(self):
            return iter(batches)

    model = TemporalGraphNetwork()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    train_physics_informed_gnn(model, optimizer, Loader(), epochs=30)
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
