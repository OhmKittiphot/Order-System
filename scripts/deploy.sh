#!/usr/bin/env bash
# Full deployment: checks -> terraform apply -> seed products -> build & upload frontend.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export AWS_REGION="${AWS_REGION:-us-east-1}"

"$ROOT/scripts/check-aws.sh"

cd "$ROOT/terraform"
[[ -f terraform.tfvars ]] || { cp terraform.tfvars.example terraform.tfvars; echo "Created terraform/terraform.tfvars from the example - review it."; }
terraform init -input=false
terraform fmt -check -recursive || echo "(formatting differences shown above; run 'terraform fmt' to fix)"
terraform validate
terraform plan -input=false -out=tfplan
terraform apply -input=false tfplan
rm -f tfplan

python3 "$ROOT/scripts/seed_products.py"
"$ROOT/scripts/deploy-frontend.sh"

echo
echo "Deployed. Next steps:"
echo "  1. Create an admin:  scripts/create-admin.sh admin@example.com 'StrongPassw0rd'"
echo "  2. Open the frontend: $(terraform -chdir="$ROOT/terraform" output -raw frontend_url)"
echo "  3. Run the end-to-end test: python3 scripts/e2e_test.py --help"
