# app/models/gnn.py
import torch
import torch.nn as nn
import torch.nn.functional as F

class TemporalGraphNetwork(nn.Module):
    def __init__(self, in_channels: int = 3, hidden_channels: int = 32, out_channels: int = 1):
        super(TemporalGraphNetwork, self).__init__()
        from torch_geometric.nn import GATConv
        
        # Spatial Graph Attention Layers (GAT)
        self.conv1 = GATConv(in_channels, hidden_channels, heads=2, concat=False)
        self.conv2 = GATConv(hidden_channels, hidden_channels, heads=2, concat=False)
        
        # Temporal Recurrent Layer (GRU) to capture sequence of events over time
        self.rnn = nn.GRU(hidden_channels, hidden_channels, batch_first=True)
        
        # Edge prediction
        self.edge_pred = nn.Sequential(
            nn.Linear(hidden_channels * 2, hidden_channels),
            nn.ReLU(),
            nn.Linear(hidden_channels, out_channels)
        )

    def forward(self, x, edge_index, h_state=None):
        # 1. Spatial Message Passing via Graph Attention
        spatial_h1 = F.elu(self.conv1(x, edge_index))
        spatial_h2 = F.elu(self.conv2(spatial_h1, edge_index))
        
        # 2. Temporal Processing
        # Reshape for GRU: [num_nodes, seq_len=1, hidden_channels]
        spatial_h2_seq = spatial_h2.unsqueeze(1)
        temporal_out, h_state_new = self.rnn(spatial_h2_seq, h_state)
        temporal_h = temporal_out.squeeze(1)
        
        # 3. Dynamic Edge Risk Prediction
        row, col = edge_index[0], edge_index[1]
        edge_features = torch.cat([temporal_h[row], temporal_h[col]], dim=1)
        
        return torch.sigmoid(self.edge_pred(edge_features)), h_state_new

    def export_to_onnx(self, filepath: str):
        """
        Exports the model to ONNX format for accelerated deployment.
        Uses representative dummy inputs to trace graph execution.
        """
        import os
        # Create dummy inputs matching typical sizes (e.g., 10 nodes, 15 edges)
        dummy_x = torch.randn(10, 3)
        dummy_edge_index = torch.tensor([
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 0],
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 9]
        ], dtype=torch.long)
        dummy_h_state = torch.zeros(1, 10, 32)
        
        # Set to eval mode before exporting
        self.eval()
        
        # Ensure parent directories exist
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        
        # Export the model
        torch.onnx.export(
            self,
            (dummy_x, dummy_edge_index, dummy_h_state),
            filepath,
            input_names=["x", "edge_index", "h_state"],
            output_names=["predictions", "h_state_new"],
            dynamic_axes={
                "x": {0: "num_nodes"},
                "edge_index": {1: "num_edges"},
                "h_state": {1: "num_nodes"},
                "predictions": {0: "num_edges"},
                "h_state_new": {1: "num_nodes"}
            },
            opset_version=15
        )


def compute_physics_loss(predictions, edge_index, metrics, features):
    """
    Computes physics-informed risk constraints across the logistics network topology.
    Vectorized representation to preserve backpropagation pipelines and maximize performance.
    
    Includes:
    1. Hydrodynamic weather strain limits
    2. Port queue capacity boundaries
    3. Mass flow conservation constraints (inflow vs. outflow divergence)
    """
    num_edges = edge_index.size(1)
    if num_edges == 0:
        return torch.tensor(0.0, requires_grad=True, device=predictions.device)

    # Ensure predictions are flat for predictable matching shapes [num_edges]
    pred_risk = predictions.squeeze()

    # Extract source (u) and destination (v) indices across all edges simultaneously
    u_indices = edge_index[0]
    v_indices = edge_index[1]

    # --- 1. Hydrodynamic Boundary Constraint (Vectorized) ---
    # Fetch weather parameters for both endpoints across all paths
    weather_u = features[u_indices, 0]
    weather_v = features[v_indices, 0]
    weather_strain = (weather_u + weather_v) / 2.0

    # Calculate violations where weather > 0.7 
    weather_violation = F.relu(weather_strain - pred_risk)
    weather_mask = (weather_strain > 0.7).float()
    
    # Isolate active violations using the conditional bitmask
    weather_loss = torch.sum((weather_violation ** 2) * weather_mask)

    # --- 2. Port Queue Capacity Constraint (Vectorized) ---
    # Extract destination node congestion metrics directly via vectorized index mapping
    dest_congestion = features[v_indices, 1]

    # Calculate capacity breaches where destination port congestion > 0.8
    congestion_violation = F.relu(dest_congestion - pred_risk)
    congestion_mask = (dest_congestion > 0.8).float()
    
    congestion_loss = torch.sum((congestion_violation ** 2) * congestion_mask)

    # --- 3. Flow Conservation Constraint (Mass Flow) ---
    # Sum of risk inflow vs outflow at nodes should be bounded to prevent isolated high-risk loops
    num_nodes = features.size(0)
    inflow = torch.zeros(num_nodes, device=predictions.device)
    outflow = torch.zeros(num_nodes, device=predictions.device)
    
    inflow.index_add_(0, v_indices, pred_risk)
    outflow.index_add_(0, u_indices, pred_risk)
    
    flow_divergence = torch.abs(inflow - outflow)
    flow_loss = torch.sum(flow_divergence ** 2)

    # Combine losses and normalize by the total number of valid edges
    total_physics_penalty = weather_loss + congestion_loss + 0.1 * flow_loss
    
    return total_physics_penalty / (num_edges + 1e-6)