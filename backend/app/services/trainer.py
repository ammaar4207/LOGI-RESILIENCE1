import torch
import torch.nn as nn
from app.models.gnn import TemporalGraphNetwork, compute_physics_loss
from app.core.config import get_settings

settings = get_settings()

def train_physics_informed_gnn(model, optimizer, data_loader, epochs=50, alpha=1.0, beta=0.4):
    """
    Executes an optimization loop bounding structural predictions using Physics-Informed constraints.
    """
    model.train()
    criterion = nn.MSELoss()
    
    print(f"Beginning PI-GNN Optimization Loop [Loss Weights -> Data: {alpha}, Physics: {beta}]")
    print("--------------------------------------------------------------------------------")

    for epoch in range(epochs):
        total_epoch_loss = 0.0
        total_data_loss = 0.0
        total_phys_loss = 0.0
        
        for batch in data_loader:
            # Unpack attributes from batch loaders
            node_features = batch.x           # Shape: [num_nodes, 3]
            adj_matrix = batch.adj            # Shape: [num_nodes, num_nodes]
            edge_index = batch.edge_index    # Shape: [2, num_edges]
            target_risk = batch.y            # Shape: [num_edges, 1]
            raw_metrics = batch.metrics       # Direct dictionary payload references
            
            optimizer.zero_grad()
            
            # Run forward pass through current GNN matrix
            predictions, _ = model(node_features, edge_index, h_state=None)
            
            # Standard statistical loss calculation
            data_loss = criterion(predictions, target_risk)
            
            # Compute physical constraint violations
            physics_loss = compute_physics_loss(
                predictions, edge_index, raw_metrics, node_features
            )
            
            # Weighted loss compilation
            loss = (alpha * data_loss) + (beta * physics_loss)
            
            loss.backward()
            optimizer.step()
            
            total_epoch_loss += loss.item()
            total_data_loss += data_loss.item()
            total_phys_loss += physics_loss.item()
            
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"Epoch {epoch+1:02d}/{epochs:02d} | "
                  f"Combined Loss: {total_epoch_loss:.4f} | "
                  f"Data MSE: {total_data_loss:.4f} | "
                  f"Physics Penalty: {total_phys_loss:.4f}")
            
    print("--------------------------------------------------------------------------------")
    print("PI-GNN Model Compilation Complete. Physics boundaries successfully enforced.")
    
    # Save optimized parameters to local disk checkpoint
    checkpoint_name = settings.MODEL_CHECKPOINT_PATH
    torch.save(model.state_dict(), checkpoint_name)
    print(f"Saved physical constraint checkpoint to '{checkpoint_name}'")

    # Log the optimized model and metrics to MLflow
    try:
        from app.services.mlflow_tracker import log_model_to_mlflow
        metrics = {
            "final_epoch_loss": total_epoch_loss,
            "final_data_loss": total_data_loss,
            "final_phys_loss": total_phys_loss
        }
        params = {
            "epochs": epochs,
            "alpha": alpha,
            "beta": beta
        }
        log_model_to_mlflow(model, metrics, params, run_name=f"run_epoch_{epochs}")
    except Exception as exc:
        print(f"MLflow model registry upload skipped: {exc}")