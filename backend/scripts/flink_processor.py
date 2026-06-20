import json
import logging
import os
import requests
from pyflink.common import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import FlinkKafkaConsumer, FlinkKafkaProducer
from pyflink.common.serialization import SimpleStringSchema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FlinkProcessor")


def process_stream():
    """
    High-performance PyFlink job to process logistics telemetry.
    Consumes raw environmental telemetry from Kafka, enriches it with real-time
    weather parameters via the OpenWeatherMap API using the WEATHER_API_KEY,
    and sinks the enriched data back into Kafka for the GNN engine.
    """
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    kafka_props = {
        'bootstrap.servers': 'kafka:9092',
        'group.id': 'flink-processor-group',
        'auto.offset.reset': 'latest'
    }

    # 1. Source: Raw Telemetry
    try:
        consumer = FlinkKafkaConsumer(
            topics='logistics.raw_telemetry',
            deserialization_schema=SimpleStringSchema(),
            properties=kafka_props
        )
        stream = env.add_source(consumer)
    except Exception as e:
        logger.error(f"Failed to connect to Kafka. Ensure Flink Kafka Connector JARs are installed. {e}")
        return

    # 2. Map Function: Parse JSON, query OpenWeatherMap, and enrich telemetry
    def enrich_data(data_str):
        try:
            payload = json.loads(data_str)
            strains = payload.get("strains", {})
            weather_api_key = os.getenv("WEATHER_API_KEY", "")

            # Mapping of port IDs to their actual coordinates for OpenWeather queries
            coords_map = {
                "sgsin": (1.3521, 103.8198),
                "sgstr": (1.25, 103.8),
                "cnsha": (31.2304, 121.4737),
                "cnnbo": (29.8683, 121.5440),
                "krpus": (35.1796, 129.0756),
                "egsuz": (29.9668, 32.5498),
                "nlrtm": (51.9244, 4.4777),
                "deham": (53.5511, 9.9937),
                "beant": (51.2194, 4.4025),
                "uslax": (33.74, -118.26),
                "usnyc": (40.7128, -74.0060),
                "aejea": (25.0112, 55.0612),
                "omsll": (17.0151, 54.0924),
                "inmun": (18.9387, 72.8258),
                "lkcmb": (6.9271, 79.8612),
                "zadur": (29.8587, 31.0218),
                "nglos": (6.4654, 3.4064),
                "mypkg": (3.0033, 101.3854),
                "cnhkg": (22.3193, 114.1694),
                "brssz": (-23.9535, -46.3015),
            }

            for node_id, metrics in strains.items():
                node_clean = node_id.strip().lower()
                lat, lon = coords_map.get(node_clean, (0.0, 0.0))
                weather_strain = metrics.get("weather", 0.2)

                # Fetch real-time weather details if API key and coordinates are available
                if weather_api_key and weather_api_key != "mock" and (lat != 0.0 or lon != 0.0):
                    try:
                        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={weather_api_key}&units=metric"
                        resp = requests.get(url, timeout=3.0)
                        if resp.status_code == 200:
                            wdata = resp.json()
                            wind_speed = float(wdata.get("wind", {}).get("speed", 0.0))
                            weather_main = (wdata.get("weather") or [{}])[0].get("main", "").lower()
                            
                            # Dynamic weather strain computation logic
                            base_strain = min(1.0, wind_speed / 25.0)
                            if weather_main in ("thunderstorm", "snow", "squall"):
                                base_strain = min(1.0, base_strain + 0.4)
                            elif weather_main in ("rain", "drizzle"):
                                base_strain = min(1.0, base_strain + 0.2)
                            
                            weather_strain = base_strain
                            logger.info(f"Flink enriched weather for {node_id}: {weather_strain} (wind={wind_speed} m/s)")
                    except Exception as e:
                        logger.warning(f"Flink Weather API call failed for {node_id}: {e}")

                metrics["weather"] = round(weather_strain, 3)

                # Classification label
                if weather_strain > 0.75:
                    metrics["weather_alert"] = "CRITICAL_STORM"
                elif weather_strain > 0.45:
                    metrics["weather_alert"] = "WARNING_STORM"
                else:
                    metrics["weather_alert"] = "NOMINAL"

            payload["flink_processed"] = True
            payload["enriched_strains"] = strains
            return json.dumps(payload)
        except Exception as e:
            logger.error(f"Error in Flink map function: {e}")
            return data_str

    enriched_stream = stream.map(enrich_data, output_type=Types.STRING())

    # 3. Sink: Enriched telemetry topic
    producer = FlinkKafkaProducer(
        topic='logistics.telemetry',
        serialization_schema=SimpleStringSchema(),
        producer_config=kafka_props
    )
    enriched_stream.add_sink(producer)

    logger.info("Submitting PyFlink Job: Logistics Telemetry Processor")
    env.execute("Logi-Resilience PyFlink Stream")


if __name__ == '__main__':
    process_stream()
