output "backend_service_url" {
  description = "Public URL for Backend FastAPI Simulation Service."
  value       = google_cloud_run_v2_service.backend.uri
}

output "frontend_service_url" {
  description = "Public URL for Frontend Next.js Management Console."
  value       = google_cloud_run_v2_service.frontend.uri
}

output "bigquery_audit_dataset" {
  description = "BigQuery dataset ID for SEBI immutable audit logs."
  value       = google_bigquery_dataset.audit_logs.dataset_id
}

output "compliance_storage_bucket" {
  description = "Cloud Storage bucket name for regulatory circulars and audit artifacts."
  value       = google_storage_bucket.compliance_storage.name
}

output "engine_service_account_email" {
  description = "Service account email running the agentic engine workloads."
  value       = google_service_account.engine_sa.email
}

output "vertex_ai_endpoint_name" {
  description = "Vertex AI serving endpoint name."
  value       = google_vertex_ai_endpoint.endpoint.name
}
