Assignment 2 - Cloud Services Exercises - Response to Criteria
================================================

Instructions
------------------------------------------------
- Keep this file named A2_response_to_criteria.md, do not change the name
- Upload this file along with your code in the root directory of your project
- Upload this file in the current Markdown format (.md extension)
- Do not delete or rearrange sections.  If you did not attempt a criterion, leave it blank
- Text inside [ ] like [eg. S3 ] are examples and should be removed


Overview
------------------------------------------------

- **Name:** Yu-Kuan, Lin
- **Student number:** n11233885
- **Partner name (if applicable):** 
- **Application name:** LeafLab
- **Two line description:** LeafLab helps analyze plant leaves with simple uploads and one-click processes. It uses an ML model to segment leaves from images
- **EC2 instance name or ID:** i-0cbea2447dfa10fbd

------------------------------------------------

### Core - First data persistence service

- **AWS service name:** S3
- **What data is being stored?:** Processed images
- **Why is this service suited to this data?:** Object storage is ideal for large, unstructured files, also it supports pre-signed URLs for secure browser uploads and downloads
- **Why is are the other services used not suitable for this data?:** RDS not efficient for large binaries. DynamoDB has size limit, so it is not for big images
- **Bucket/instance/table name:** n11233885-leaflab-data 
- **Video timestamp:** 00:00 ~ 01:02
- **Relevant files:**
    - /app/s3.py
    - /app/db_models.py
    - /app/routers/files.py
    - /app/routers/jobs.py
    - /app/config.py
    - /frontend/src/components/FileUpload.jsx

### Core - Second data persistence service

- **AWS service name:**  RDS (PostgreSQL)
- **What data is being stored?:**  Structured application metadata: 'Users' (Cognito-linked sub, email, role) 'Files', 'Jobs' , 'Results'
- **Why is this service suited to this data?:** I need relational integrity (PK, FK), ACID transactions, and flexible querying. PostgreSQL also gives indexes, constraints, and JSONB for semi-structured field
- **Why is are the other services used not suitable for this data?:** S3 : No relational queries; DynamoDB : Global ordering is hard, my app often need ORDER BY 'created_at' DESC across all table. Additionally, dynamoDB transactions exist, but they’re limited and add retry/condition complexity
- **Bucket/instance/table name:** users, files, results, jobs 
- **Video timestamp:** 00:00 ~ 01:02
- **Relevant files:**
    - /app/db_models.py
    - /app/db.py
    - /app/routers/jobs.py
    - /app/routers/files.py

### Third data service

- **AWS service name:** 
- **What data is being stored?:** 
- **Why is this service suited to this data?:** 
- **Why is are the other services used not suitable for this data?:** 
- **Bucket/instance/table name:** 
- **Video timestamp:**
- **Relevant files:**
    -

### S3 Pre-signed URLs

- **S3 Bucket names:** n11233885-leaflab-data 
- **Video timestamp:** 01:02 ~ 01:28
- **Relevant files:**
    - /app/s3.py
    - /app/db_models.py
    - /app/routers/files.py
    - /app/routers/jobs.py
    - /app/config.py
    - /frontend/src/components/FileUpload.jsx

### In-memory cache

- **ElastiCache instance name:** Memcached cluster : n11233885-leaflab 
- **What data is being cached?:**  1. S3 HEAD metadata per object under keys like s3:head:{key} 2. Pre-signed GET URLs under keys like s3:url:{key}
- **Why is this data likely to be accessed frequently?:**  My 'files' and 'jobs 'API endpoints repeatedly list files and generate view/download/preview links, requiring S3 HEAD requests and pre-signed GET URLs. Without caching, each page load increases latency and costs due to repeated requests
- **Video timestamp:** 01:27 ~ 01:56
- **Relevant files:**
    - /app/cache.py
    - /app/s3.py

### Core - Statelessness

- **What data is stored within your application that is not stored in cloud data services?:**  None. The app is stateless all data lives in RDS/S3 and config in Parameter Store Secrets Manager
- **Why is this data not considered persistent state?:** 
- **How does your application ensure data consistency if the app suddenly stops?:** 
If something fails or stops unexpectedly, users with an admin role can use the 'requeue' function to manually requeue jobs. This will reload data from S3 and RDS and maintain data integrity by changing the job status
- **Relevant files:**
    - /app/s3.py
    - /app/db_models.py
    - /app/cache.py
    - /app/routers/files.py
    - /app/routers/jobs.py

### Graceful handling of persistent connections

- **Type of persistent connection and use:** 
- **Method for handling lost connections:** 
- **Relevant files:**
    -


### Core - Authentication with Cognito

- **User pool name:** n11233885-leaflab-a2
- **How are authentication tokens handled by the client?:**  After login at /{version}/cognito/login (or Google via /{version}/cognito/callback), the API returns tokens in JSON. The client keeps the access_token in app state or secure storage. Every request to the API sends Authorization: Bearer <ACCESS_TOKEN>. The server is stateless and verifies the JWT using Cognito JWKS. For protected routes (Jobs, Files), the FastAPI dependency current_user (in deps_cognito.py) calls cognito_current_user (in auth_cognito.py) to validate the token and load/create the user. If the token is missing/invalid/expired, the API returns 401
- **Video timestamp:** 01:57 ~ 02:53
- **Relevant files:**
    - /app/routers/auth_cognito.py
    - /app/deps.py 
    - /app/routers/files.py
    - /app/routers/jobs.py

### Cognito multi-factor authentication

- **What factors are used for authentication:** 
- **Video timestamp:**
- **Relevant files:**
    -

### Cognito federated identities

- **Identity providers used:** Google
- **Video timestamp:** 02:53 ~ 03:33
- **Relevant files:**
    - /app/routers/auth_cognito.py
    - /app/deps.py 
    - /app/routers/files.py
    - /app/routers/jobs.py
    

### Cognito groups

- **How are groups used to set permissions?:** Permissions are driven by Cognito groups. The API reads the cognito:groups claim from the JWT and maps it to an app role. I use two groups: user and admin. A user have access to their own jobs and files, but cannot requeue any job. An admin can list files/jobs for any owner (via owner_id), access any result preview, and requeue any job. These checks are enforced per request in 'deps.current_user' on protected routes
- **Video timestamp:** 03:34 ~ 04:29
- **Relevant files:**
    - /app/routers/auth_cognito.py
    - /app/deps.py 
    - /app/routers/files.py
    - /app/routers/jobs.py

### Core - DNS with Route53

- **Subdomain**: https://n11233885.leaflab.cab432.com/
- **Video timestamp:** 04:30 ~ 05:01

### Parameter store

- **Parameter names:** 
    /n11233885/CACHE_URL, 
    /n11233885/COGNITO_CLIENT_ID, 
    /n11233885/COGNITO_DOMAIN, 
    /n11233885/COGNITO_LOGOUT_REDIRECT_URI, 
    /n11233885/COGNITO_REDIRECT_URI, 
    /n11233885/COGNITO_REGION, 
    /n11233885/COGNITO_USER_POOL_ID, 
    /n11233885/CORS_ALLOW_ORIGINS, 
    /n11233885/S3_BUCKET, 
    /n11233885/SAM_CHECKPOINT, 
    /n11233885/SAM_MODEL_TYPE, 
    /n11233885/VERSION
- **Video timestamp:** 05:02 ~ 05:26 (AWS Console), 05:39 ~ 06:53 (source code)
- **Relevant files:**
    - /app/config.py
    - /app/cache.py
    - /app/s3.py
    - /app/main.py
    - /app/processing.py
    - /app/routers/auth_cognito.py
    - /app/routers/files.py


### Secrets manager

- **Secrets names:** 
    /n11233885/DATABASE_URL (includes Username/password)
    /n11233885/COGNITO_CLIENT_SECRET
- **Video timestamp:** 05:26 ~ 05:38(AWS Console), 05:39 ~ 06:53 (source code)
- **Relevant files:**
    - /app/db.py
    - /app/routers/auth_cognito.py

### Infrastructure as code

- **Technology used:** Terraform
- **Services deployed:**  Cognito, Memcached, Route 53, S3, Secret Manager (insert/update/delete), Parameter Store (update/insert/delete)
- **Video timestamp:** 06:53 ~ 07:20
- **Relevant files:**
    - /infra/**

### Other (with prior approval only)

- **Description:**
- **Video timestamp:**
- **Relevant files:**
    -

### Other (with prior permission only)

- **Description:**
- **Video timestamp:**
- **Relevant files:**
    -