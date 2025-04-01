from kubernetes import client, config
import os
import logging

logger = logging.getLogger(__name__)

class KubernetesClient:
    def __init__(self):
        """Initialize Kubernetes client - works both in-cluster and out-of-cluster"""
        try:
            # Try to load in-cluster config first
            config.load_incluster_config()
            logger.info("Using in-cluster Kubernetes configuration")
        except config.ConfigException:
            # Fall back to kubeconfig file
            config.load_kube_config()
            logger.info("Using kubeconfig file for Kubernetes configuration")
        
        self.api_client = client.ApiClient()
        self.core_v1 = client.CoreV1Api(self.api_client)
        self.apps_v1 = client.AppsV1Api(self.api_client)
        self.namespace = os.getenv("NAMESPACE", "default")
        
        # Bot pod configuration
        self.bot_image = os.getenv("BOT_IMAGE", "gcr.io/your-project/bot:latest")
        self.transcription_service = os.getenv("TRANSCRIPTION_SERVICE", "transcription-service:8080")
    
    def create_bot_pod(self, user_id, meeting_id):
        """Create a new bot pod for specific user and meeting"""
        pod_name = f"bot-{user_id}-{meeting_id}"
        
        # Check if pod already exists
        try:
            existing_pod = self.core_v1.read_namespaced_pod(
                name=pod_name, 
                namespace=self.namespace
            )
            logger.info(f"Pod {pod_name} already exists")
            return {"status": "exists", "pod_name": pod_name}
        except client.rest.ApiException as e:
            if e.status != 404:
                logger.error(f"Error checking pod existence: {e}")
                raise
        
        # Create pod
        container = client.V1Container(
            name="bot",
            image=self.bot_image,
            env=[
                client.V1EnvVar(name="USER_ID", value=user_id),
                client.V1EnvVar(name="MEETING_ID", value=meeting_id),
                client.V1EnvVar(name="TRANSCRIPTION_SERVICE", value=self.transcription_service)
            ],
            resources=client.V1ResourceRequirements(
                requests={"cpu": "100m", "memory": "128Mi"},
                limits={"cpu": "500m", "memory": "256Mi"}
            )
        )
        
        pod_spec = client.V1PodSpec(containers=[container])
        pod_template = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=pod_name,
                labels={
                    "app": "bot",
                    "user-id": user_id,
                    "meeting-id": meeting_id
                }
            ),
            spec=pod_spec
        )
        
        try:
            self.core_v1.create_namespaced_pod(
                namespace=self.namespace,
                body=pod_template
            )
            logger.info(f"Created pod {pod_name}")
            return {"status": "created", "pod_name": pod_name}
        except client.rest.ApiException as e:
            logger.error(f"Error creating pod: {e}")
            raise
    
    def delete_bot_pod(self, user_id, meeting_id=None):
        """Delete a bot pod by user_id and optionally meeting_id"""
        try:
            if meeting_id:
                pod_name = f"bot-{user_id}-{meeting_id}"
                self.core_v1.delete_namespaced_pod(
                    name=pod_name,
                    namespace=self.namespace
                )
                logger.info(f"Deleted pod {pod_name}")
                return {"status": "deleted", "pod_name": pod_name}
            else:
                # Delete all pods for user
                pod_list = self.core_v1.list_namespaced_pod(
                    namespace=self.namespace,
                    label_selector=f"app=bot,user-id={user_id}"
                )
                for pod in pod_list.items:
                    self.core_v1.delete_namespaced_pod(
                        name=pod.metadata.name,
                        namespace=self.namespace
                    )
                    logger.info(f"Deleted pod {pod.metadata.name}")
                return {"status": "deleted", "count": len(pod_list.items)}
        except client.rest.ApiException as e:
            logger.error(f"Error deleting pod: {e}")
            raise
    
    def get_bot_status(self, user_id):
        """Get status of all bot pods for a user"""
        try:
            pod_list = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app=bot,user-id={user_id}"
            )
            
            result = []
            for pod in pod_list.items:
                meeting_id = pod.metadata.labels.get("meeting-id", "unknown")
                status = pod.status.phase
                result.append({
                    "pod_name": pod.metadata.name,
                    "user_id": user_id,
                    "meeting_id": meeting_id,
                    "status": status,
                    "creation_time": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
                })
            
            return result
        except client.rest.ApiException as e:
            logger.error(f"Error getting pod status: {e}")
            raise 