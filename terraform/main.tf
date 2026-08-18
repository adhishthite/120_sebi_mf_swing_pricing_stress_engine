terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  default_labels = {
    app         = var.app_name
    environment = var.environment
    managed_by  = "terraform"
    domain      = "bfsi-mutual-funds"
    regulation  = "sebi-swing-pricing"
  }
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

locals {
  service_prefix = "${var.app_name}-${var.environment}"
}
