import pathlib
import aws_cdk as cdk
import yaml

from stacks.guardrails import GuardrailsStack
from stacks.label import LabelStack
from stacks.monitoring import MonitoringStack
from stacks.pipeline import PipelineStack
from stacks.serve import ServeStack
from stacks.storage import StorageStack

cfg = yaml.safe_load((pathlib.Path(__file__).parent.parent / "config.yaml").read_text())
env = cdk.Environment(account="631603562462", region=cfg["aws"]["region"])

app = cdk.App()
storage = StorageStack(app, "plateloop-storage", cfg=cfg, env=env)
label = LabelStack(app, "plateloop-label", cfg=cfg, storage=storage, env=env)
ServeStack(app, "plateloop-serve", cfg=cfg, storage=storage, label_queue=label.queue, env=env)
monitoring = MonitoringStack(app, "plateloop-monitoring", cfg=cfg, env=env)
PipelineStack(app, "plateloop-pipeline", cfg=cfg, storage=storage, monitoring=monitoring, env=env)
GuardrailsStack(app, "plateloop-guardrails", cfg=cfg, env=env)
cdk.Tags.of(app).add("project", cfg["tags"]["project"])
app.synth()
