variable "region" {
  type    = string
}

variable "ns" {
  type    = string

}

# ---------- SSM Parameters (non-secret) ----------
variable "s3_bucket" {
  type    = string
  default = "n11233885-leaflab-data"
}

variable "sam_model_type" {
  type    = string
  default = "vit_b"
}

variable "sam_checkpoint" {
  type    = string
  default = "/models/sam_vit_b_01ec64.pth"
}

variable "version_prefix" {
  type    = string
  default = "v1"
}

variable "cors_allow_origins" {
  type    = string

}



# ---------- Secrets ----------



variable "database_url" {
  type    = string

}




#-------------Tag------------
variable "common_tags" {
  type = map(string)

}
