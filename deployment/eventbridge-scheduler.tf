# Terraform 설정 for EventBridge Scheduler + ECS Fargate
# AWS 계정에서 terraform apply 한 번만 실행

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "ap-northeast-2"
}

# Variables
variable "account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "ecr_repository" {
  description = "ECR Repository Name"
  default     = "perfacto-ai"
}

variable "ecs_cluster_name" {
  description = "ECS Cluster Name"
  default     = "perfacto-ai-cluster"
}

variable "subnet_ids" {
  description = "VPC Subnet IDs"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security Group ID"
  type        = string
}

# ECS Cluster
resource "aws_ecs_cluster" "perfacto_ai" {
  name = var.ecs_cluster_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "Perfacto-AI Cluster"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "perfacto_ai" {
  name              = "/ecs/perfacto-ai"
  retention_in_days = 7

  tags = {
    Name = "Perfacto-AI Logs"
  }
}

# IAM Role for ECS Task Execution
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "perfacto-ai-ecs-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Secrets Manager 접근 권한
resource "aws_iam_role_policy" "ecs_secrets_policy" {
  name = "perfacto-ai-secrets-policy"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:ap-northeast-2:${var.account_id}:secret:perfacto-ai/*"
      }
    ]
  })
}

# IAM Role for ECS Task (runner.py에서 사용)
resource "aws_iam_role" "ecs_task_role" {
  name = "perfacto-ai-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# S3, Polly 등 접근 권한
resource "aws_iam_role_policy" "ecs_task_policy" {
  name = "perfacto-ai-task-policy"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "polly:SynthesizeSpeech",
          "s3:PutObject",
          "s3:GetObject",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

# EventBridge Scheduler Role
resource "aws_iam_role" "scheduler_role" {
  name = "perfacto-ai-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "scheduler_policy" {
  name = "perfacto-ai-scheduler-policy"
  role = aws_iam_role.scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = "arn:aws:ecs:ap-northeast-2:${var.account_id}:task-definition/perfacto-ai-task:*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_task_execution_role.arn,
          aws_iam_role.ecs_task_role.arn
        ]
      }
    ]
  })
}

# EventBridge Scheduler - 과학 (매일 오전 9시)
resource "aws_scheduler_schedule" "science_daily" {
  name       = "perfacto-ai-science-daily"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 9 * * ? *)"
  schedule_expression_timezone = "Asia/Seoul"

  target {
    arn      = aws_ecs_cluster.perfacto_ai.arn
    role_arn = aws_iam_role.scheduler_role.arn

    ecs_parameters {
      task_definition_arn = "arn:aws:ecs:ap-northeast-2:${var.account_id}:task-definition/perfacto-ai-task"
      launch_type         = "FARGATE"
      platform_version    = "LATEST"

      network_configuration {
        subnets          = var.subnet_ids
        security_groups  = [var.security_group_id]
        assign_public_ip = true
      }
    }

    input = jsonencode({
      containerOverrides = [
        {
          name = "perfacto-ai-container"
          command = [
            "--job-config",
            "deployment/production_job_config.yaml",
            "--job-name",
            "weekly-science-premium"
          ]
        }
      ]
    })
  }
}

# EventBridge Scheduler - 체스 (매일 오후 2시)
resource "aws_scheduler_schedule" "chess_daily" {
  name       = "perfacto-ai-chess-daily"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 14 * * ? *)"
  schedule_expression_timezone = "Asia/Seoul"

  target {
    arn      = aws_ecs_cluster.perfacto_ai.arn
    role_arn = aws_iam_role.scheduler_role.arn

    ecs_parameters {
      task_definition_arn = "arn:aws:ecs:ap-northeast-2:${var.account_id}:task-definition/perfacto-ai-task"
      launch_type         = "FARGATE"
      platform_version    = "LATEST"

      network_configuration {
        subnets          = var.subnet_ids
        security_groups  = [var.security_group_id]
        assign_public_ip = true
      }
    }

    input = jsonencode({
      containerOverrides = [
        {
          name = "perfacto-ai-container"
          command = [
            "--job-config",
            "deployment/production_job_config.yaml",
            "--job-name",
            "weekly-chess-premium"
          ]
        }
      ]
    })
  }
}

# EventBridge Scheduler - 역사 (매일 오후 7시)
resource "aws_scheduler_schedule" "history_daily" {
  name       = "perfacto-ai-history-daily"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 19 * * ? *)"
  schedule_expression_timezone = "Asia/Seoul"

  target {
    arn      = aws_ecs_cluster.perfacto_ai.arn
    role_arn = aws_iam_role.scheduler_role.arn

    ecs_parameters {
      task_definition_arn = "arn:aws:ecs:ap-northeast-2:${var.account_id}:task-definition/perfacto-ai-task"
      launch_type         = "FARGATE"
      platform_version    = "LATEST"

      network_configuration {
        subnets          = var.subnet_ids
        security_groups  = [var.security_group_id]
        assign_public_ip = true
      }
    }

    input = jsonencode({
      containerOverrides = [
        {
          name = "perfacto-ai-container"
          command = [
            "--job-config",
            "deployment/production_job_config.yaml",
            "--job-name",
            "weekly-history-premium"
          ]
        }
      ]
    })
  }
}

# Outputs
output "ecs_cluster_name" {
  value = aws_ecs_cluster.perfacto_ai.name
}

output "task_execution_role_arn" {
  value = aws_iam_role.ecs_task_execution_role.arn
}

output "task_role_arn" {
  value = aws_iam_role.ecs_task_role.arn
}
