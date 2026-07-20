resource "oci_identity_dynamic_group" "builder" {
  compartment_id = var.tenancy_ocid
  name           = "${var.name_prefix}-builder"
  description    = "The disposable DQ08 GitHub Actions builder instance."
  matching_rule  = "instance.id = '${oci_core_instance.builder.id}'"
  freeform_tags  = local.common_tags
}

# OCI lifecycle rules execute as the regional Object Storage service, not as
# the user applying this stack. Oracle requires this root-compartment policy
# before the service can delete expired objects or abort multipart uploads.
resource "oci_identity_policy" "object_lifecycle_service" {
  compartment_id = var.tenancy_ocid
  name           = "${var.name_prefix}-object-lifecycle"
  description    = "Permit the regional Object Storage service to enforce lifecycle rules in the dedicated DQ08 compartment."

  statements = [
    "Allow service objectstorage-${var.region} to manage object-family in compartment id ${var.compartment_ocid}",
  ]
}

resource "oci_identity_policy" "builder_staging_upload" {
  compartment_id = var.compartment_ocid
  name           = "${var.name_prefix}-staging-upload"
  description    = "Permit only the DQ08 builder instance principal to stage release objects."

  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.builder.name} to read buckets ${local.iam_scope} where target.bucket.name = '${oci_objectstorage_bucket.staging.name}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.builder.name} to manage objects ${local.iam_scope} where all {target.bucket.name = '${oci_objectstorage_bucket.staging.name}', any {request.permission = 'OBJECT_CREATE', request.permission = 'OBJECT_OVERWRITE', request.permission = 'OBJECT_INSPECT', request.permission = 'OBJECT_READ'}}",
  ]
}
