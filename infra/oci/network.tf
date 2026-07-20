resource "oci_core_vcn" "builder" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.name_prefix}-vcn"
  dns_label      = "dq08vcn"
  freeform_tags  = local.common_tags
}

resource "oci_core_internet_gateway" "builder" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.builder.id
  display_name   = "${var.name_prefix}-internet"
  enabled        = true
  freeform_tags  = local.common_tags
}

resource "oci_core_route_table" "builder" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.builder.id
  display_name   = "${var.name_prefix}-public-routes"
  freeform_tags  = local.common_tags

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.builder.id
  }
}

resource "oci_core_security_list" "builder" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.builder.id
  display_name   = "${var.name_prefix}-restricted"
  freeform_tags  = local.common_tags

  ingress_security_rules {
    description = "SSH from the explicitly trusted administrator CIDR"
    protocol    = "6"
    source      = var.admin_ssh_cidr
    source_type = "CIDR_BLOCK"
    stateless   = false

    tcp_options {
      min = 22
      max = 22
    }
  }

  # Required for path-MTU discovery; this does not expose an application port.
  ingress_security_rules {
    description = "IPv4 path MTU discovery"
    protocol    = "1"
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    stateless   = false

    icmp_options {
      type = 3
      code = 4
    }
  }

  # The builder needs only web traffic, DNS, and NTP. All rules are stateful.
  egress_security_rules {
    description      = "HTTPS for GitHub, OCI, package, and source downloads"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "6"
    stateless        = false

    tcp_options {
      min = 443
      max = 443
    }
  }

  egress_security_rules {
    description      = "HTTP for package repositories that have not redirected yet"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "6"
    stateless        = false

    tcp_options {
      min = 80
      max = 80
    }
  }

  egress_security_rules {
    description      = "DNS over UDP"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "17"
    stateless        = false

    udp_options {
      min = 53
      max = 53
    }
  }

  egress_security_rules {
    description      = "DNS over TCP"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "6"
    stateless        = false

    tcp_options {
      min = 53
      max = 53
    }
  }

  egress_security_rules {
    description      = "NTP time synchronization"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "17"
    stateless        = false

    udp_options {
      min = 123
      max = 123
    }
  }

  egress_security_rules {
    description      = "DHCP address configuration"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "17"
    stateless        = false

    udp_options {
      min = 67
      max = 67
    }
  }
}

resource "oci_core_subnet" "builder" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.builder.id
  cidr_block                 = var.subnet_cidr
  display_name               = "${var.name_prefix}-public-subnet"
  dns_label                  = "builder"
  prohibit_public_ip_on_vnic = false
  route_table_id             = oci_core_route_table.builder.id
  security_list_ids          = [oci_core_security_list.builder.id]
  freeform_tags              = local.common_tags
}
