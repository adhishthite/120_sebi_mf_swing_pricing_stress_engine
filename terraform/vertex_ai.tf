# ---------------------------------------------------------------------------
# Cloud Storage Bucket for Regulatory Circulars & Artifacts
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "compliance_storage" {
  name                        = "${local.service_prefix}-compliance-data"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 365 # Retain compliance audit documents for 1 year
    }
  }
}

# ---------------------------------------------------------------------------
# BigQuery Dataset & Tables for SEBI Immutable Audit Ledger
# ---------------------------------------------------------------------------

resource "google_bigquery_dataset" "audit_logs" {
  dataset_id                  = replace("${var.app_name}_audit_logs", "-", "_")
  friendly_name               = "SEBI Mutual Fund Swing Pricing Audit Dataset"
  description                 = "Immutable regulatory audit ledger recording stress test runs, CEL guardrails, and HITL approvals."
  location                    = var.region
  default_table_expiration_ms = null # Retain indefinitely for compliance
}

resource "google_bigquery_table" "swing_pricing_traces" {
  dataset_id          = google_bigquery_dataset.audit_logs.dataset_id
  table_id            = "swing_pricing_traces"
  deletion_protection = false

  schema = <<EOF
[
  {
    "name": "session_id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Unique session identifier"
  },
  {
    "name": "trace_id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "OpenTelemetry trace ID"
  },
  {
    "name": "timestamp",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "Simulation UTC execution timestamp"
  },
  {
    "name": "aum",
    "type": "FLOAT",
    "mode": "REQUIRED",
    "description": "Total fund AUM in INR"
  },
  {
    "name": "net_outflow_pct",
    "type": "FLOAT",
    "mode": "REQUIRED",
    "description": "Net redemption outflow as percentage of AUM"
  },
  {
    "name": "applied_swing_factor_pct",
    "type": "FLOAT",
    "mode": "REQUIRED",
    "description": "Applied swing factor percentage"
  },
  {
    "name": "optimal_strategy",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Selected liquidation strategy (PRO_RATA, WATERFALL, OPTIMIZED)"
  },
  {
    "name": "compliance_status",
    "type": "BOOLEAN",
    "mode": "REQUIRED",
    "description": "Overall CEL statutory compliance status"
  },
  {
    "name": "hitl_status",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Human-In-The-Loop status (ACTIVE, HELD, APPROVED, REJECTED)"
  },
  {
    "name": "audit_payload_json",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Full serialized audit JSON payload"
  }
]
EOF
}

# ---------------------------------------------------------------------------
# Service Account & IAM Bindings
# ---------------------------------------------------------------------------

resource "google_service_account" "engine_sa" {
  account_id   = "${var.app_name}-sa"
  display_name = "SEBI Swing Pricing Engine Service Account"
  description  = "Service Account used by Cloud Run services for Vertex AI, BigQuery, and Cloud Storage access."
}

resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.engine_sa.email}"
}

resource "google_project_iam_member" "bigquery_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.engine_sa.email}"
}

resource "google_project_iam_member" "storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.engine_sa.email}"
}

resource "google_project_iam_member" "cloud_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.engine_sa.email}"
}

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.engine_sa.email}"
}

# ---------------------------------------------------------------------------
# Vertex AI Endpoint Placeholder
# ---------------------------------------------------------------------------

resource "google_vertex_ai_endpoint" "endpoint" {
  name         = "${local.service_prefix}-endpoint"
  display_name = "SEBI Swing Pricing AI Serving Endpoint"
  location     = var.region
  description  = "Vertex AI Serving Endpoint for Model Tuning and Agentic Evaluation."
}
