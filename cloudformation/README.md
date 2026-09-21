# Release dispatcher AWS infrastructure

`release-dispatch.yaml` creates the AWS resources used by
`.github/workflows/dispatch.yml`:

- a private, SSE-S3 encrypted release-state bucket;
- the GitHub Actions OIDC provider, unless the account already has one; and
- the `duckdb-release-dispatch` role with access only to that bucket.

The bucket and a newly created OIDC provider use CloudFormation retention
policies, so deleting the stack does not delete release state or a provider
that other GitHub roles may have started using.

## Deploy into a new account

Authenticate as an administrator in the target account, choose a globally
unique bucket name, and deploy the stack in `us-east-2`:

```sh
aws cloudformation deploy \
  --stack-name duckdb-release-dispatch \
  --template-file cloudformation/release-dispatch.yaml \
  --region us-east-2 \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ReleaseStateBucketName=duckdb-release-state-ACCOUNT_ID
```

Replace `ACCOUNT_ID` with the target AWS account ID. If the account already
has the GitHub Actions OIDC provider, add:

```text
CreateGitHubOidcProvider=false
```

The existing provider must have `sts.amazonaws.com` in its client ID list.

After deployment, read the stack outputs and set these GitHub repository
variables to the corresponding values:

- `AWS_ROLE_ARN` from `AwsRoleArn`
- `AWS_REGION` from `AwsRegion`
- `RELEASE_STATE_BUCKET` from `ReleaseStateBucket`

For example, inspect all outputs with:

```sh
aws cloudformation describe-stacks \
  --stack-name duckdb-release-dispatch \
  --region us-east-2 \
  --query 'Stacks[0].Outputs' \
  --output table
```

The default trust policy permits only the `main` branch of
`duckdb/duckdb-workflow-trigger`. Override `GitHubOrganization`,
`GitHubRepository`, or `GitHubBranch` during deployment only when migrating a
different repository or branch.

## Existing manually created resources

Do not run a normal deployment in an account where the bucket or role already
exists under the selected names: CloudFormation cannot automatically adopt
them. This template is intended for the next clean-account migration. Existing
resources can instead be brought under the stack with a planned CloudFormation
resource import.
