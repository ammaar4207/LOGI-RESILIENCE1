# Logi-Resilience Production AWS Infrastructure Definition
# Provider: AWS
# Architecture: VPC + ECS Fargate + RDS PostgreSQL + ElastiCache Redis + ALBs

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "production"
}

# 1. Virtual Private Cloud (VPC)
resource "aws_vpc" "logi_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = {
    Name        = "logi-resilience-vpc"
    Environment = var.environment
  }
}

# Subnets (2x Public, 2x Private across AZs)
resource "aws_subnet" "public_a" {
  vpc_id            = aws_vpc.logi_vpc.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
  map_public_ip_on_launch = true
  tags = { Name = "logi-subnet-public-a" }
}

resource "aws_subnet" "public_b" {
  vpc_id            = aws_vpc.logi_vpc.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"
  map_public_ip_on_launch = true
  tags = { Name = "logi-subnet-public-b" }
}

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.logi_vpc.id
  cidr_block        = "10.0.10.0/24"
  availability_zone = "us-east-1a"
  tags = { Name = "logi-subnet-private-a" }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.logi_vpc.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "us-east-1b"
  tags = { Name = "logi-subnet-private-b" }
}

# Gateways
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.logi_vpc.id
  tags   = { Name = "logi-igw" }
}

resource "aws_eip" "nat_eip" {
  domain = "vpc"
}

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat_eip.id
  subnet_id     = aws_subnet.public_a.id
  tags          = { Name = "logi-nat-gateway" }
}

# Routing
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.logi_vpc.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "logi-public-rt" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.logi_vpc.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }
  tags = { Name = "logi-private-rt" }
}

resource "aws_route_table_association" "pub_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "pub_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "priv_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "priv_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private.id
}

# 2. Database Layer (RDS PostgreSQL)
resource "aws_db_subnet_group" "db_subnet" {
  name       = "logi-db-subnet-group"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

resource "aws_security_group" "db_sg" {
  name        = "logi-db-security-group"
  description = "Allow inbound traffic from ECS services to PostgreSQL"
  vpc_id      = aws_vpc.logi_vpc.id
  
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks_sg.id]
  }
}

resource "aws_db_instance" "postgres" {
  identifier             = "logi-db-postgres"
  allocated_storage      = 20
  db_name                = "logiresilience"
  engine                 = "postgres"
  engine_version         = "15.4"
  instance_class         = "db.t4g.micro"
  username               = "logi_admin"
  password               = aws_secretsmanager_secret_version.db_pass.secret_string
  db_subnet_group_name   = aws_db_subnet_group.db_subnet.name
  vpc_security_group_ids = [aws_security_group.db_sg.id]
  skip_final_snapshot    = true
}

# 3. Redis Caching Layer (Amazon ElastiCache)
resource "aws_elasticache_subnet_group" "redis_subnet" {
  name       = "logi-redis-subnet-group"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

resource "aws_security_group" "redis_sg" {
  name        = "logi-redis-security-group"
  description = "Allow inbound Redis traffic from ECS Fargate"
  vpc_id      = aws_vpc.logi_vpc.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks_sg.id]
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id          = "logi-redis-cluster"
  description                   = "Logi-Resilience cache & Celery broker"
  node_type                     = "cache.t4g.micro"
  num_cache_clusters            = 1
  parameter_group_name          = "default.redis7"
  port                          = 6379
  subnet_group_name             = aws_elasticache_subnet_group.redis_subnet.name
  security_group_ids            = [aws_security_group.redis_sg.id]
  at_rest_encryption_enabled    = true
  transit_encryption_enabled   = true
}

# 4. ECS Fargate Compute Layer
resource "aws_ecs_cluster" "ecs_cluster" {
  name = "logi-resilience-cluster"
}

resource "aws_security_group" "ecs_tasks_sg" {
  name        = "logi-ecs-tasks-sg"
  description = "Security Group for ECS Fargate Tasks"
  vpc_id      = aws_vpc.logi_vpc.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Load Balancers
resource "aws_lb" "alb" {
  name               = "logi-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]
}

resource "aws_security_group" "alb_sg" {
  name   = "logi-alb-sg"
  vpc_id = aws_vpc.logi_vpc.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Secrets Management
resource "aws_secretsmanager_secret" "db_password_secret" {
  name = "logi-db-password-production"
}

resource "aws_secretsmanager_secret_version" "db_pass" {
  secret_id     = aws_secretsmanager_secret.db_password_secret.id
  secret_string = "SecureProdDbPass2026!"
}

# Output URLs
output "alb_dns_name" {
  value       = aws_lb.alb.dns_name
  description = "The public application entry DNS address."
}
