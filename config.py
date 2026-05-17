import os


class Config:
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    output_dir: str = os.getenv("OUTPUT_DIR", "output")
