data "aws_iam_policy_document" "gha_trust" {
  count = local.use_github_actions_oidc ? 1 : 0
  statement {
    effect = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_owner}/${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  count = local.use_github_actions_oidc ? 1 : 0
  name  = "${local.name}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.gha_trust[0].json
  tags = { Name = "${local.name}-gha" }
}

# For a throwaway account/stack only—replace with least-privilege for long-lived production.
resource "aws_iam_role_policy_attachment" "github_admin" {
  count = local.use_github_actions_oidc ? 1 : 0
  role  = aws_iam_role.github_actions[0].name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
