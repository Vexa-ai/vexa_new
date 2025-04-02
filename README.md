# Vexa - Bot Management System

A container-based Bot Management system that automatically deploys and manages user-specific bot containers in a Kubernetes cluster, monitors their health, and integrates with a load-balanced transcription service.

## Architecture

The system consists of several key components:

1. **Gateway API** - Entry point for client requests, routes to appropriate services
2. **Bot Manager API** - Handles lifecycle of bot containers and transcription storage
3. **Transcription Service** - Load-balanced service for processing transcriptions
4. **Bot Containers** - User-specific containers running the Vexa Bot for meeting participation
5. **Redis** - Used by Celery for task queue and caching
6. **PostgreSQL** - Database for storing transcriptions and metadata
7. **Celery Workers** - Background workers for monitoring bot containers

## Bot Implementation

This system uses the [Vexa Bot](https://github.com/Vexa-ai/vexa-bot) for joining and participating in virtual meetings. The Vexa Bot:
- Runs in a containerized environment
- Can join Google Meet meetings 
- Automatically handles waiting room and participant detection
- Captures meeting transcriptions and forwards them to the transcription service

## Local Development Setup

The project includes Docker Compose configuration for easy local development.

### Prerequisites for Development

- Docker and Docker Compose installed
- Git
- Make (optional, but recommended)

### Getting Started with Local Development

1. Clone the repository and set up the environment:

```bash
git clone <repository-url> vexa
cd vexa
make setup  # This will clone the Vexa Bot repository
```

2. Start the local development environment:

```bash
# Build all services (including the bot)
make build

# If you have Make installed:
make up

# Without Make:
docker-compose up -d
```

This will start all the required services:
- Gateway API at http://localhost:8000
- Bot Manager API at http://localhost:8080
- Transcription Service at http://localhost:8081
- Redis (internal)
- PostgreSQL (accessible on port 5432)
- Celery worker (internal)

3. Check that everything is running:

```bash
# If you have Make installed:
make ps

# Without Make:
docker-compose ps
```

4. View logs:

```bash
# All services
make logs

# Specific service
make logs-gateway
make logs-bot-manager
make logs-transcription

# Without Make:
docker-compose logs -f [service_name]
```

### Testing Bot Creation

You can create a test bot using the API or the provided shortcuts:

```bash
# Using Make with custom bot:
make run-bot USER=user123 MEETING=meeting456 MEETING_URL=https://meet.google.com/your-meeting-code

# Using curl:
curl -X POST http://localhost:8000/bot/run \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "meeting_id": "meeting456",
    "meeting_url": "https://meet.google.com/your-meeting-code",
    "meeting_title": "Test Meeting"
  }'
```

### Bot Configuration Options

The bot accepts several environment variables:
- `USER_ID` - User identifier
- `MEETING_ID` - Meeting identifier
- `MEETING_URL` - URL of the Google Meet meeting
- `TRANSCRIPTION_SERVICE` - Endpoint to send transcriptions to

Additional configuration options are available in the bot config file.

### Stopping the Services

```bash
# If you have Make installed:
make down

# Without Make:
docker-compose down
```

### Cleaning Up

To remove all containers and volumes:

```bash
# If you have Make installed:
make clean

# Without Make:
docker-compose down -v
```

## Production Deployment

For production deployment, the project uses Kubernetes with Helm charts.

### Prerequisites for Production

- Google Cloud Platform account with GKE enabled
- Google Artifact Registry configured
- `kubectl` CLI installed and configured
- `helm` CLI installed
- `gcloud` CLI installed and configured
- Docker installed (for building images)

## Project Structure

```
vexa/
├── docker/                  # Dockerfiles for all components
├── helm/                    # Helm charts for Kubernetes deployment
├── k8s/                     # Kubernetes resources not managed by Helm
├── vexa-bot/                # Vexa Bot implementation (cloned separately)
└── src/                     # Source code for all components
    ├── gateway/             # Gateway API service
    ├── bot-manager/         # Bot Manager API service
    ├── bot/                 # Bot container integration code
    └── transcription-service/ # Transcription processing service
```

## Setup & Deployment for Production

### 1. Build and Push Docker Images

First, clone the Vexa Bot repository:

```bash
git clone https://github.com/Vexa-ai/vexa-bot.git
```

Then build and push all Docker images to Google Artifact Registry:

```bash
# Set your GCP project ID
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1

# Configure Docker for Artifact Registry
gcloud auth configure-docker $REGION-docker.pkg.dev

# Build and push Gateway API
docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/vexa/gateway:latest -f docker/gateway/Dockerfile .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/vexa/gateway:latest

# Build and push Bot Manager API
docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/vexa/bot-manager:latest -f docker/bot-manager/Dockerfile .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/vexa/bot-manager:latest

# Build and push Transcription Service
docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/vexa/transcription-service:latest -f docker/transcription-service/Dockerfile .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/vexa/transcription-service:latest

# Build and push Bot container
docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/vexa/bot:latest -f docker/bot/Dockerfile .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/vexa/bot:latest
```

### 2. Create GKE Cluster

Create a GKE cluster with node autoscaling enabled:

```bash
# Create cluster with node autoscaling
gcloud container clusters create vexa-cluster \
  --region=$REGION \
  --num-nodes=3 \
  --machine-type=e2-standard-4 \
  --enable-autoscaling \
  --min-nodes=1 \
  --max-nodes=10 \
  --scopes=gke-default,storage-rw
```

### 3. Create Kubernetes Namespace

Apply the namespace configuration:

```bash
kubectl apply -f k8s/namespace.yaml
```

### 4. Configure Cluster Autoscaler

Apply the cluster autoscaler configuration:

```bash
kubectl apply -f k8s/cluster-autoscaler.yaml
```

### 5. Deploy with Helm

Update the `values.yaml` with your specific configuration:

```bash
# Update the image registry to match your GCP project
sed -i "s/gcr.io\/your-project/$REGION-docker.pkg.dev\/$PROJECT_ID\/vexa/g" helm/vexa/values.yaml

# Update any other values as needed (domain names, resource limits, etc.)
```

Now deploy the application using Helm:

```bash
helm install vexa ./helm/vexa --namespace vexa
```

### 6. Verify the Deployment

Check that all components are running:

```bash
kubectl get pods -n vexa
```

The system should have the following components running:
- Gateway API pods
- Bot Manager API pods
- Transcription Service pods 
- Redis pod
- PostgreSQL pod
- Celery worker pods

## API Usage

### Starting a Bot

```bash
curl -X POST https://api.example.com/bot/run \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "meeting_id": "meeting456",
    "meeting_url": "https://meet.google.com/xxx-xxxx-xxx", 
    "meeting_title": "Team Weekly Sync"
  }'
```

### Stopping a Bot

```bash
curl -X POST https://api.example.com/bot/stop \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "meeting_id": "meeting456"
  }'
```

### Getting Bot Status

```bash
curl -X GET https://api.example.com/bot/status/user123
```

### Retrieving Transcriptions

```bash
curl -X GET https://api.example.com/transcript/user123/meeting456
```

## Scaling

The system is designed to scale automatically:

1. **Pod Autoscaling**: Each service has Horizontal Pod Autoscaler (HPA) configured to scale based on CPU utilization.
2. **Node Autoscaling**: The GKE cluster has node autoscaling enabled to add/remove nodes as needed.
3. **Bot Containers**: Each user gets their own isolated bot container, which is created on demand.

## Monitoring & Maintenance

### Checking Bot Status

```bash
kubectl get pods -n vexa -l app=bot
```

### Viewing Service Logs

```bash
# Gateway API logs
kubectl logs -n vexa deployment/gateway

# Bot Manager API logs
kubectl logs -n vexa deployment/bot-manager

# Transcription Service logs
kubectl logs -n vexa deployment/transcription-service

# Specific bot logs (replace with actual pod name)
kubectl logs -n vexa bot-user123-meeting456
```

### Accessing the Database

```bash
# Port forward PostgreSQL to your local machine
kubectl port-forward -n vexa svc/postgres-service 5432:5432

# Connect using psql
psql -h localhost -U postgres -d vexa
```

## Troubleshooting

### Common Issues

1. **Bot containers not starting**:
   - Check Bot Manager logs for errors
   - Verify RBAC permissions for bot-manager service account
   - Check if the bot image exists in the registry

2. **Bot cannot join meetings**:
   - Ensure the meeting URL is correct and accessible
   - Check if the meeting requires authentication
   - Verify the bot has necessary permissions to join the meeting

3. **Transcription not showing up**:
   - Check connectivity between bot containers and Transcription Service
   - Verify PostgreSQL is running and accessible
   - Check bot logs for transcription processing errors

4. **API Gateway not accessible**:
   - Check Ingress configuration
   - Verify GCP Load Balancer is properly configured
   - Check SSL certificates if using HTTPS

### Restarting Services

If needed, you can restart individual services:

```bash
kubectl rollout restart deployment/gateway -n vexa
kubectl rollout restart deployment/bot-manager -n vexa
kubectl rollout restart deployment/transcription-service -n vexa
kubectl rollout restart deployment/celery-worker -n vexa
```

## Cleanup

To remove the entire deployment:

```bash
# Delete Helm release
helm uninstall vexa -n vexa

# Delete namespace
kubectl delete namespace vexa

# Delete GKE cluster
gcloud container clusters delete vexa-cluster --region=$REGION
``` 



```mermaid
graph TD
    subgraph "Vexa System (Managed Environment - Docker Compose / Kubernetes)"
        Client -- HTTP Request (run/stop bot, get transcript) --> Gateway[Gateway API];

        Gateway -- Route Request --> BM[Bot Manager API];
        Gateway -- Route Request --> TS[Transcription Service];

        BM -- Start/Stop Container --> Infra[(Container Orchestrator API)];
        BM -- Store/Retrieve Metadata --> DB[(PostgreSQL Database)];
        BM -- Enqueue Task --> Redis[(Redis Task Queue)];

        Celery[Celery Workers] -- Monitor Bots --> Infra;
        Celery -- Read Task --> Redis;

        TS -- Store/Retrieve Transcript --> DB;

        subgraph "Running Bot Instance (Container/Pod)"
            direction LR
            BotContainer[Bot Container (vexa-bot code)];
            BotContainer -- Join Meeting --> Meeting([External Meeting\ne.g., Google Meet]);
            BotContainer -- Send Audio Stream --> WhisperWS([WhisperLive WebSocket]);
            WhisperWS -- Send Transcription Chunks --> BotContainer;
            BotContainer -- POST Transcription --> TS;
        end

        Infra -- Creates/Manages --> BotInstance[Bot Instance Container/Pod];
    end

    style Infra fill:#f9f,stroke:#333,stroke-width:2px
    style Meeting fill:#ccf,stroke:#333,stroke-width:2px
    style WhisperWS fill:#ccf,stroke:#333,stroke-width:2px

```
