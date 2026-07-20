resource "oci_objectstorage_bucket" "staging" {
  compartment_id        = var.compartment_ocid
  namespace             = data.oci_objectstorage_namespace.this.namespace
  name                  = local.staging_bucket_name
  access_type           = "NoPublicAccess"
  auto_tiering          = "Disabled"
  object_events_enabled = false
  storage_tier          = "Standard"
  versioning            = "Disabled"
  freeform_tags         = merge(local.common_tags, { Purpose = "temporary-release-staging" })

  lifecycle {
    precondition {
      condition     = var.region == local.tenancy_home_region
      error_message = "region must be the tenancy home region (${local.tenancy_home_region}) for this free pipeline."
    }
  }
}

resource "oci_objectstorage_object_lifecycle_policy" "staging" {
  namespace = data.oci_objectstorage_namespace.this.namespace
  bucket    = oci_objectstorage_bucket.staging.name

  depends_on = [oci_identity_policy.object_lifecycle_service]

  rules {
    action      = "DELETE"
    is_enabled  = true
    name        = "delete-staged-release-assets-after-three-days"
    target      = "objects"
    time_amount = 3
    time_unit   = "DAYS"
  }

  # The upload-scoped builder cannot abort failed multipart uploads itself.
  rules {
    action      = "ABORT"
    is_enabled  = true
    name        = "abort-incomplete-multipart-uploads"
    target      = "multipart-uploads"
    time_amount = 1
    time_unit   = "DAYS"
  }
}

resource "oci_objectstorage_preauthrequest" "publisher_read" {
  namespace             = data.oci_objectstorage_namespace.this.namespace
  bucket                = oci_objectstorage_bucket.staging.name
  name                  = "${var.name_prefix}-github-publisher-read"
  access_type           = "AnyObjectRead"
  bucket_listing_action = "Deny"
  time_expires          = var.staging_par_expiration

  # OCI enforces Deny but currently omits this default when reading the PAR
  # back. Ignore that API normalization so every refresh does not revoke and
  # replace the bearer URL. New and deliberately rotated PARs still send Deny.
  lifecycle {
    ignore_changes = [bucket_listing_action]
  }
}
