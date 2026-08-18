variable "project_id" {
  description = "Google Cloud Project ID where services will be provisioned."
  type        = string
  default     = "google-cloud-project"
}

variable "region" {
  description = "Primary Google Cloud Region for BFSI deployment (default Mumbai / asia-south1)."
  type        = string
  default     = "asia-south1"
}

variable "environment" {
  description = "Target deployment tier (dev, staging, prod)."
  type        = string
  default     = "prod"
}

variable "app_name" {
  description = "Application identifier prefix for resources."
  type        = string
  default     = "sebi-mf-swing-pricing"
}

variable "backend_image" {
  description = "Container image URI for Backend FastAPI Service."
  type        = string
  default     = "gcr.io/google-cloud-project/sebi-mf-backend:latest"
}

variable "frontend_image" {
  description = "Container image URI for Frontend Next.js Console."
  type        = string
  default     = "gcr.io/google-cloud-project/sebi-mf-frontend:latest"
}
