resource "oci_identity_dynamic_group" "builder" {
  compartment_id = var.tenancy_ocid
  name           = "${var.name_prefix}-builder"
  description    = "The disposable DQ08 GitHub Actions builder instance."
  matching_rule  = "instance.id = '${oci_core_instance.builder.id}'"
  freeform_tags  = local.common_tags
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
