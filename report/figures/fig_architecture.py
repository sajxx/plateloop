import sys, os; sys.path.insert(0, os.path.dirname(__file__))
from style import *
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

fig, ax = plt.subplots(figsize=(10, 6.0)); ax.set_xlim(0, 100); ax.set_ylim(0, 60); ax.axis("off")
def station(x, y, n, title, lines, fc):
    w, h = 29, 15.5
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.5", fc="white", ec=fc, lw=1.8))
    ax.add_patch(FancyBboxPatch((x, y + h - 5.2), w, 5.2, boxstyle="round,pad=0.2,rounding_size=1.5", fc=fc, ec=fc, lw=1.8))
    ax.add_patch(Circle((x + 3.2, y + h - 2.6), 1.9, fc="white", ec="none")); ax.text(x + 3.2, y + h - 2.6, str(n), ha="center", va="center", color=fc, fontsize=10, fontweight="bold")
    ax.text(x + 6.5, y + h - 2.6, title, ha="left", va="center", color="white", fontsize=10.5, fontweight="bold")
    ax.text(x + 1.8, y + h - 7, "\n".join(lines), ha="left", va="top", fontsize=8.6, color="#222", linespacing=1.55)
def arrow(p, q, c=NAVY, rad=0.0, ls="-", lw=2.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=14, color=c, lw=lw, connectionstyle=f"arc3,rad={rad}", linestyle=ls))
X = [2, 35.5, 69]; Y1, Y2 = 37, 15
station(X[0], Y1, 1, "Capture", ["API Gateway and a Lambda function", "save every image to S3 and a", "record to DynamoDB"], BLUE)
station(X[1], Y1, 2, "Serve", ["SageMaker endpoint (ml.m5.large)", "runs the PicoDet-XS plate detector", "and returns boxes and a version"], TEAL)
station(X[2], Y1, 3, "Label", ["Nova 2 Lite proposes plate boxes;", "three agreement rules accept the", "label or send it to quarantine"], NAVY)
station(X[2], Y2, 4, "Retrain", ["SageMaker Pipeline fine-tunes on 70%", "original and 30% new labels. Starts:", "weekly, 200 labels, drift, manual"], ORANGE)
station(X[1], Y2, 5, "Gate", ["The candidate must beat the live", "model on the golden set; failures", "are logged and the live model stays"], RED)
station(X[0], Y2, 6, "Release", ["Approval in the Model Registry, then", "a blue/green update with automatic", "rollback if an alarm trips"], GREEN)
mid1, mid2 = Y1 + 7.2, Y2 + 7.2
arrow((X[0] + 29.4, mid1), (X[1] - 0.4, mid1)); arrow((X[1] + 29.4, mid1), (X[2] - 0.4, mid1))
arrow((X[2] + 14.5, Y1 - 0.4), (X[2] + 14.5, Y2 + 16.0))
arrow((X[2] - 0.4, mid2), (X[1] + 29.4, mid2)); arrow((X[1] - 0.4, mid2), (X[0] + 29.4, mid2))
arrow((X[0] + 29.2, Y2 + 16.1), (X[1] + 2, Y1 - 0.5), c=GREEN, rad=-0.25, ls="--")
ax.text(25.5, 33.2, "new model serves", fontsize=7.5, color=GREEN, ha="center", va="center", fontweight="bold")
# shared services band
ax.add_patch(FancyBboxPatch((2, 1.2), 96, 6, boxstyle="round,pad=0.2,rounding_size=1.2", fc=LIGHT, ec="#C9D6E4", lw=1))
ax.text(4, 4.2, "Shared services", fontsize=8.5, color=NAVY, fontweight="bold", va="center")
ax.text(26, 4.2, "Amazon S3  |  DynamoDB  |  SQS  |  Model Registry  |  CloudWatch alarms  |  EventBridge  |  IAM", fontsize=8.5, color="#333", va="center")
ax.text(50, 58.3, "Images move clockwise through the six stations; only the gate at station 5 can replace the live model.", ha="center", va="center", fontsize=8.5, color=GRAY, style="italic")
fig.tight_layout(pad=0.3); fig.savefig(os.path.join(os.path.dirname(__file__), "fig3_1_architecture.png"), dpi=200)
