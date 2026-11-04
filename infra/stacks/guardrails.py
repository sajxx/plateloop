import aws_cdk as cdk
from aws_cdk import aws_budgets as budgets
from constructs import Construct


class GuardrailsStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, cfg: dict, **kw):
        super().__init__(scope, id, **kw)
        email, limit = cfg["alerts"]["email"], cfg["alerts"]["monthly_budget_usd"]

        def note(kind, pct):
            return budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(
                    notification_type=kind, comparison_operator="GREATER_THAN", threshold=pct,
                    threshold_type="PERCENTAGE"),
                subscribers=[budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=email)])

        budgets.CfnBudget(
            self, "Monthly",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"{cfg['project']}-monthly-budget", budget_type="COST", time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=limit, unit="USD")),
            notifications_with_subscribers=[note("ACTUAL", 50), note("ACTUAL", 80), note("FORECASTED", 100)])
