import os
import logging
import mlflow
import mlflow.pytorch
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def log_model_to_mlflow(model, metrics: dict, params: dict, run_name: str = "gnn_training"):
    """
    Logs the trained PyTorch Geometric model, metrics, and parameters to the MLflow tracking server.
    """
    try:
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
        mlflow.set_experiment("logi_resilience_gnn")

        os.environ["MLFLOW_S3_ENDPOINT_URL"] = f"http://{settings.MINIO_ENDPOINT}"
        os.environ["AWS_ACCESS_KEY_ID"] = settings.MINIO_ACCESS_KEY
        os.environ["AWS_SECRET_ACCESS_KEY"] = settings.MINIO_SECRET_KEY

        with mlflow.start_run(run_name=run_name):
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            
            # Log the PyTorch model
            mlflow.pytorch.log_model(model, "models")
            
            logger.info(f"Successfully logged model and metrics to MLflow under run '{run_name}'.")
    except Exception as e:
        logger.warning(f"MLflow tracking failed: {e}")
