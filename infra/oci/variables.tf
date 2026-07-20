variable "tenancy_ocid" {
  description = "OCID of the OCI tenancy (the root compartment)."
  type        = string

  validation {
    condition     = can(regex("^ocid1\\.tenancy\\.", var.tenancy_ocid))
    error_message = "tenancy_ocid must be an OCI tenancy OCID."
  }
}

variable "compartment_ocid" {
  description = "OCID of the compartment that will contain the builder resources."
  type        = string

  validation {
    condition     = can(regex("^ocid1\\.(compartment|tenancy)\\.", var.compartment_ocid))
    error_message = "compartment_ocid must be an OCI compartment OCID (or the tenancy OCID)."
  }
}

variable "region" {
  description = "OCI tenancy home-region identifier, for example eu-frankfurt-1. Plans fail when a different region is selected because A1 and block storage would not be Always Free."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2,3}-[a-z0-9-]+-[1-9][0-9]*$", var.region))
    error_message = "region must look like an OCI region identifier, for example eu-frankfurt-1."
  }
}

variable "availability_domain" {
  description = "Optional availability-domain name. The first AD is used when null. Override this if A1 capacity is unavailable there."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.availability_domain == null || try(length(trimspace(var.availability_domain)) > 0, false)
    error_message = "availability_domain must be null or a non-empty OCI availability-domain name."
  }
}

variable "ubuntu_image_ocid" {
  description = "Optional Ubuntu 24.04 aarch64 platform image OCID. The newest compatible image is discovered when null."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.ubuntu_image_ocid == null || try(can(regex("^ocid1\\.image\\.", var.ubuntu_image_ocid)), false)
    error_message = "ubuntu_image_ocid must be null or an OCI image OCID."
  }
}

variable "admin_ssh_cidr" {
  description = "Single trusted IPv4 CIDR allowed to SSH to the builder. A world-open CIDR is rejected."
  type        = string

  validation {
    condition     = can(cidrnetmask(var.admin_ssh_cidr)) && var.admin_ssh_cidr != "0.0.0.0/0"
    error_message = "admin_ssh_cidr must be a valid restricted IPv4 CIDR; 0.0.0.0/0 is not allowed."
  }
}

variable "ssh_public_key" {
  description = "Public SSH key installed for the Ubuntu image's default ubuntu account."
  type        = string

  validation {
    condition     = can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521))[[:space:]]+[A-Za-z0-9+/=]+", trimspace(var.ssh_public_key)))
    error_message = "ssh_public_key must be an OpenSSH RSA, Ed25519, or ECDSA public key."
  }
}

variable "github_repository" {
  description = "Repository to which the manually registered self-hosted runner belongs, in owner/name form."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use owner/name form."
  }
}

variable "name_prefix" {
  description = "Short lowercase prefix for OCI resource names."
  type        = string
  default     = "dq08-armbian"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.name_prefix))
    error_message = "name_prefix must be 3-24 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "staging_bucket_name" {
  description = "Optional Object Storage bucket name. Defaults to <name_prefix>-staging."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.staging_bucket_name == null || try(can(regex("^[A-Za-z0-9][A-Za-z0-9._-]{2,62}$", var.staging_bucket_name)), false)
    error_message = "staging_bucket_name must be null or a 3-63 character bucket name without slashes."
  }
}

variable "staging_par_expiration" {
  description = "Future RFC3339 UTC timestamp at which the publisher's read-only pre-authenticated request expires."
  type        = string

  validation {
    condition     = can(regex("^20[0-9]{2}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$", var.staging_par_expiration))
    error_message = "staging_par_expiration must be an RFC3339 UTC timestamp such as 2027-12-31T23:59:59Z."
  }
}

variable "vcn_cidr" {
  description = "IPv4 CIDR for the dedicated builder VCN."
  type        = string
  default     = "10.42.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vcn_cidr))
    error_message = "vcn_cidr must be a valid IPv4 CIDR."
  }
}

variable "subnet_cidr" {
  description = "IPv4 CIDR for the public builder subnet; it must be contained by vcn_cidr."
  type        = string
  default     = "10.42.0.0/24"

  validation {
    condition     = can(cidrnetmask(var.subnet_cidr))
    error_message = "subnet_cidr must be a valid IPv4 CIDR."
  }
}

variable "freeform_tags" {
  description = "Additional free-form tags applied to taggable OCI resources."
  type        = map(string)
  default     = {}
}
