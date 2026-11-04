"""Chapter text for the project report. Each chapter function receives a Builder `b` (see build_report.py)."""

TITLE = "Automated MLOps Pipeline for License Plate Recognition on AWS"


def abstract(b):
    b.add(b.abstract_heading())
    paras = [
        "License plate recognition is used for parking, toll collection, gate access and traffic enforcement. Its first and most important step is finding the plate inside the camera image. A plate detector that works well on the day it is trained slowly becomes less reliable, because lighting, camera angles, weather and vehicle types change, and the people who maintain it rarely have time to collect new examples, label them and retrain by hand.",
        "Most student and industry projects stop once a detector has been trained. Without an automatic way to capture the images a model sees, label them, test new versions, release them safely and watch for trouble, the model is never updated and its accuracy quietly falls. Labelling is the costliest part, because every training image needs a box drawn around each plate.",
        "This project, Automated MLOps Pipeline for License Plate Recognition on AWS, builds a closed loop that keeps a compact plate detector up to date with very little manual work. The loop runs entirely on Amazon Web Services inside the credits of the AWS Free plan. The detector is a PicoDet-XS model of about 0.7 million parameters that finds the position of every plate in an image.",
        "The pipeline has six stations. Every image sent to the service is stored and described by a few simple statistics. A SageMaker endpoint returns the plate boxes. A second model, Amazon Nova 2 Lite, proposes boxes for the stored images, and three agreement rules decide which proposals become training labels. A SageMaker Pipeline retrains the detector when a weekly schedule, 200 new labels, a drift alarm or a manual request asks for it. A release rule then compares the new model with the live one on a fixed golden set, and only a clear improvement is approved and deployed with a blue/green update and automatic rollback.",
        "The detector was trained on 22,906 annotated images and checked on 2,546 validation images. The check also showed that 1,865 of the validation images come from the same source pictures as training images, so a stricter held-out set of 681 images was built, and from it a golden set of 150 images. The detector reaches an average precision of 0.923 at an overlap threshold of 0.50 on the full validation set, 0.768 on the held-out sources and 0.761 on the golden set. At the chosen score threshold of 0.4 it finds 71.7% of the plates on the held-out sources with a precision of 87.4%.",
        "The served model files are 1.8 MB, and one image is processed in 17 ms on two CPU threads, the same number as the two virtual CPUs of the serving instance. Drift measurements show that the average confidence falls and the share of images with no plate found rises as images become darker, blurrier or noisier, and the alarm rule fires from a blur of 3 pixels, noise of 35 grey levels or a brightness factor of 0.15. The complete system is estimated to use about 26 US dollars of the 100 dollars of sign-up credit. The result is a repeatable, low-cost way to keep a plate detector accurate after it has been deployed.",
    ]
    for p in paras:
        b.add(b.abstract_para(p))
        b.add(b.abstract_spacer())
    b.add(b.keywords("License Plate Detection; MLOps; Amazon SageMaker; Automatic Labelling; Model Drift; Cloud Deployment"))


def ch1(b):
    b.chapter(1, "INTRODUCTION")
    b.p("A camera at a car park entrance, a toll booth or a residential gate produces thousands of images every day. To turn those images into useful information, software must first find the licence plate in each picture and then read its characters. This first step is called plate detection, and every later step depends on it. If the plate is missed or the box is drawn in the wrong place, nothing that follows can be correct.")
    b.p("A detector that lives only on the computer where it was trained helps nobody else, and one that is never updated slowly loses accuracy. This project therefore treats the plate detector as a service that must be kept healthy after it is released. It connects image capture, automatic labelling, retraining, testing, release and monitoring into one loop that runs on Amazon Web Services. This report describes the data, the design, the implementation, the measured results and the limits of the finished system.")
    b.h3("1.1 Background of the Study")
    b.p("Automatic licence plate recognition has been studied for many years. Early systems relied on hand-written rules for colour and shape, while current systems use neural networks that learn to find plates in difficult conditions such as dim light, motion blur and sharp viewing angles (Silva and Jung, 2018; Laroca et al., 2018). Two families of detectors dominate. Two-stage detectors, such as Faster R-CNN, first propose regions and then classify them (Ren et al., 2015). One-stage detectors, such as YOLO and the PicoDet family, predict boxes in a single pass and are much faster (Redmon et al., 2016; Yu et al., 2021).")
    b.p("Speed matters because many plate readers run on modest hardware. PicoDet was designed for low-power processors, and its smallest versions use a backbone named LCNet that is tuned for ordinary CPUs (Cui et al., 2021; Yu et al., 2021). A model of this kind can be served from a small, inexpensive cloud machine without any graphics card, which is why it suits a project that must stay within the free credits of a student account.")
    b.p("A trained model is only the beginning of the work. Sculley et al. (2015) explain that machine learning systems collect hidden maintenance costs, because their behaviour depends on data that keeps changing. Amershi et al. (2019) report the same difficulty from inside a large software company. The set of practices that addresses it is called machine learning operations, or MLOps. It covers recording experiments, automating training and testing, releasing models safely, and watching their behaviour in use (Kreuzberger et al., 2023).")
    b.p("One cause of declining accuracy is drift, which means that the images the model sees in daily use slowly differ from the images it was trained on (Gama et al., 2014; Lu et al., 2020). A new camera, a change of season or a different mix of vehicles is enough. The usual response is to collect fresh images, label them and retrain. Labelling is the slowest and most expensive step, so recent systems let a second, general-purpose model suggest labels and then keep only the suggestions that can be trusted, an idea known as self-training (Xie et al., 2020).")
    b.h3("1.2 Problem Statement and Motivation")
    b.p("**Problem statement.** Given a stream of images from cameras, keep a licence plate detector accurate over time, at low cost and with little manual work, by automatically capturing the images it sees, labelling them, retraining the detector, testing the new version, releasing it only when it is clearly better, and raising an alarm when the images begin to change.")
    b.p("Without such a loop three problems follow. First, the team has no record of what the model sees in real use, so changes in the images go unnoticed. Second, labelling new images by hand is slow, so retraining is postponed again and again. Third, a hastily retrained model can be worse than the one it replaces, and without a fixed test and a safe release method the damage reaches users before anyone notices.")
    b.p("The motivation is to show that a small team or a student can build this loop from managed cloud services, and keep it inside the free credits of an AWS account. Amazon SageMaker AI supplies the endpoint, the training jobs, the pipeline and the model registry. Amazon Bedrock supplies the model that proposes labels. Storage, queues, functions and alarms come from S3, SQS, Lambda and CloudWatch. SageMaker Ground Truth, the usual AWS labelling service, is closed to new customers and is not part of the Free plan (AWS, 2026h; 2026b), so the labelling stage had to be built another way.")
    b.p("**Scope.** The system finds the position of licence plates and returns boxes with confidence scores. It does not read the characters on the plate. It works on still pictures only, with one detector architecture and one AWS Region, Asia Pacific (Sydney), which AWS assigns to new accounts in India (AWS, 2026c). It uses public or consented images only, because licence plates are personal data.")
    b.h3("1.3 Objectives of the Study")
    b.p("The main objective of this project is to design, implement and run an end-to-end MLOps pipeline on AWS that keeps a licence plate detector accurate after release. The specific objectives are:")
    for t in [
        "Serve the PicoDet-XS plate detector from a SageMaker endpoint behind a public interface that stores every image and a small set of statistics about it.",
        "Label stored images automatically with Amazon Nova 2 Lite, accepting a proposal only when it agrees with the live detector or passes a shape and size check.",
        "Retrain the detector with a SageMaker Pipeline that is started by a schedule, a label count, a drift alarm or a manual request, and that allows only one run at a time.",
        "Release a new model only when it beats the live model on a fixed golden set, using a blue/green update that rolls back by itself when an alarm trips.",
        "Measure the detector, the labelling rules, the drift signals and the cost, and keep the whole system inside the AWS Free plan credits.",
    ]:
        b.bullet(t)
    b.h3("1.4 Significance of the Study")
    b.p("For operators of plate readers, the system replaces occasional manual retraining with a routine that runs by itself and reports what it does. For students and small teams, it is a complete, working example of how the parts of an MLOps system fit together on a managed cloud, using only services that the Free plan supports.")
    b.p("The contribution is practical rather than algorithmic. The project shows the full operational path for an image detector: capture, serve, label, retrain, test, release and monitor. It also shows several lessons that are easy to miss, such as the need to separate validation images by their source picture (Section 5.1), the care needed when a general model is used as a labeller (Section 3.3), and the way a plain confidence statistic can warn of changing images (Section 5.3).")
    b.p("The stakeholders who benefit most are parking and toll operators, who need a detector that keeps pace with their cameras, road authorities, who need fewer missed plates, and teaching staff, who need a reproducible reference project for the MLOps and AWS course.")
    b.h3("1.5 Organization of the Report")
    b.p("The report has six chapters. Chapter 1 introduces the background, the problem, the objectives and the significance of the study. Chapter 2 reviews related work on plate detection and on the operation of machine learning systems and identifies the gaps. Chapter 3 explains the six-station architecture, the modules and the models and formulas used. Chapter 4 describes the environment, the tools, the implementation steps, the dataset and the key code. Chapter 5 presents the measured results and interprets them. Chapter 6 concludes the report and lists future work.")


def ch2(b):
    b.chapter(2, "LITERATURE REVIEW")
    b.objective("To analyse past work on licence plate detection and on the operational practices needed to keep machine learning models accurate in use, to highlight the gaps, and to position the present study.")
    b.h3("2.1 Related Work")
    b.h4("Licence plate detection")
    b.p("Silva and Jung (2018) built a system for unconstrained scenes in which the camera views the vehicle at steep angles. Their network first finds the vehicle, then finds and corrects the plate, and finally reads it, and it was tested on difficult photographs. Laroca et al. (2018) used the YOLO detector for each step of a real-time reader. On a public data set of 2,000 frames from 101 videos it reached a recognition rate of 93.53% at 47 frames per second, and on a second data set with moving cameras it reached 78.33% at 35 frames per second, ahead of the commercial trial versions they compared against.")
    b.p("These studies concentrate on how accurate a detector can be at one moment. They train a model, report a score and stop. They do not describe what happens when the cameras or the weather change after the system has been installed.")
    b.h4("Small and fast detectors")
    b.p("Yu et al. (2021) introduced PP-PicoDet, a family of detectors made for mobile processors. The smallest model in the family has fewer than one million parameters, and the larger ones reach higher accuracy at a still modest cost. The design combines a light backbone, a feature-merging neck and a head that predicts the box edges directly. Cui et al. (2021) describe PP-LCNet, the CPU-friendly backbone used by these detectors. Detection quality is normally measured with the average precision defined for the COCO benchmark, which requires a predicted box to overlap the true box by a stated amount (Lin et al., 2014). The present project uses the same measure.")
    b.h4("Machine learning operations")
    b.p("Sculley et al. (2015) argue that machine learning systems carry a special kind of technical debt, because code, data and settings depend on each other in ways that are hard to see. Amershi et al. (2019) describe how software teams struggle with data management, model versions and testing. Kreuzberger et al. (2023) combine a literature review, a review of tools and interviews with practitioners to define MLOps and to set out its principles, such as automation, versioned artefacts, continuous training and continuous monitoring, together with a reference architecture.")
    b.h4("Drift and self-training")
    b.p("Gama et al. (2014) and Lu et al. (2020) survey concept drift, the change over time in the relation between the inputs of a model and the right answer. They group the work into detecting drift, understanding it and adapting to it. Xie et al. (2020) show that a model can improve by learning from labels that another model has produced for unlabelled images, provided the labels are filtered and noise is added during learning. Their experiments are on image classification.")
    b.p("Table 2.1 summarises the studies discussed and how the present work differs from them.")
    b.caption("Table 2.1", "Summary of related studies")
    b.table([1500, 2700, 2300, 2526], ["Study", "Setting and models", "Scope reported", "Gap addressed here"], [
        ["Silva and Jung (2018)", "Unconstrained scenes; vehicle and plate networks", "Detection and reading of difficult photographs", "Accuracy at one moment; no life cycle after training"],
        ["Laroca et al. (2018)", "YOLO-based reader tested on two public data sets", "93.53% at 47 FPS and 78.33% at 35 FPS", "Fixed models; no retraining, labelling or monitoring"],
        ["Yu et al. (2021)", "PicoDet family on the COCO benchmark", "Accuracy and speed on mobile CPUs", "General objects; no serving or update loop"],
        ["Sculley et al. (2015)", "Machine learning systems in practice", "Hidden technical debt and risks", "Describes the risks; no working plate system"],
        ["Kreuzberger et al. (2023)", "MLOps review, tool survey and interviews", "Definition, principles, architecture", "Generic architecture; no AWS build with cost and results"],
        ["Lu et al. (2020)", "Review of concept drift methods", "Detecting, understanding and adapting to drift", "Methods only; not applied to a deployed detector"],
        ["Xie et al. (2020)", "Self-training for image classification", "Gains from model-made labels", "Classification, not detection; no release control"],
    ])
    b.p("The studies in the table are summarised from their published abstracts and describe their main focus. They do not claim to cover the operation of a deployed plate detector, which is the focus of this project.")
    b.h3("2.2 Research Gaps")
    b.p("Reading the literature against the needs of a plate reader that stays in service shows the following gaps. First, plate detection studies concentrate on accuracy on a fixed test set and say little about what happens after installation. Second, MLOps studies describe general principles and reference architectures but rarely show a complete, small-scale build with its cost.")
    b.p("Third, labelling is treated as a separate problem, although it is the step that decides whether retraining is affordable. Fourth, evaluation sets are often built by splitting one pool of images at random, which can place near-copies of a training image in the test set and make the score look better than it is. Fifth, tutorials rarely explain how to stay inside the free credits of a cloud account, where a single forgotten server can use up the whole balance.")
    b.p("This study addresses these gaps by building the full loop on AWS, by letting a general model propose labels under strict agreement rules, by separating the golden set from the training sources, and by recording the cost of each part of the system.")
    b.h4("Key Challenges of the Existing System")
    for t in [
        "**Models that are never updated.** A plate detector that is trained once loses accuracy as the images change.",
        "**No record of real use.** Without capturing the images and their results, changes in the data go unseen.",
        "**Costly labelling.** Drawing a box on every new image by hand makes frequent retraining unaffordable.",
        "**Untrustworthy automatic labels.** A general model can draw loose or wrong boxes, and training on them can make the detector worse.",
        "**Risky releases.** A new model that has not been compared with the live one on a fixed test can lower accuracy for every user.",
        "**Runaway cost.** A cloud endpoint left running overnight can use a large part of a student credit balance.",
    ]:
        b.numbered(t)


def ch3(b):
    b.chapter(3, "SYSTEM ARCHITECTURE")
    b.objective("To explain the technical approach, the stages and modules of the pipeline, and the algorithms and models used.")
    b.h3("3.1 Proposed System/Methodology")
    b.p("The system is organised as a loop of six stations. Each station has one job and leaves behind a stored result that the next station uses. Station 1 captures every image and its statistics. Station 2 serves the detector. Station 3 labels stored images. Station 4 retrains the detector. Station 5 decides whether the new model is better. Station 6 releases the approved model and watches it. Monitoring runs across all stations and can start a new round.")
    b.p("Three principles guide the design. First, nothing is changed by hand while the loop is running. Every action is a function, a job or a rule that can be repeated and logged. Second, a model is never trusted because it is new. Only a comparison with the live model on a fixed golden set can replace it, and a rejected model is simply recorded. Third, every service is chosen from the list that the AWS Free plan supports (AWS, 2026b), and everything that costs money while idle can be switched off by a script.")
    b.p("The detector is a PicoDet-XS model trained on 22,906 annotated images. It is trained with a 2,000-image subset and fine-tuned on later rounds with a mixture of about 70% original images and 30% newly labelled images, so that it keeps what it already knows. The data are divided into a training set, a validation set and a golden set, as described in Section 4.4. The golden set is never used for training.")
    b.h3("3.2 System Architecture Diagram")
    b.p("Figure 3.1 shows the six stations and the loop that connects them. Table 3.1 lists, for each station, its input, the result it stores and the AWS services involved. Figure 3.2 shows how a retraining request travels from its trigger to a released model.")
    b.figure("fig3_1_architecture.png", "Figure 3.1", "System architecture: six stations from image capture to safe release, closed into a loop.")
    b.caption("Table 3.1", "Stations, stored results and AWS services")
    b.table([1500, 2000, 2700, 2826], ["Station", "Input", "Stored result", "Main AWS services"], [
        ["1 Capture", "Image from a client", "Image in S3 and a row with its statistics", "API Gateway, Lambda, S3, DynamoDB"],
        ["2 Serve", "Image", "Boxes, scores and the model version", "SageMaker real-time endpoint"],
        ["3 Label", "Stored image", "Accepted label, or an image sent to quarantine", "SQS, Lambda, Bedrock (Nova 2 Lite), S3"],
        ["4 Retrain", "Original data and new labels", "Candidate model files", "SageMaker Pipeline and training job"],
        ["5 Gate", "Candidate and live models", "Metrics report and a pass or fail decision", "SageMaker processing, Model Registry"],
        ["6 Release", "Approved model", "Updated endpoint; version shown in every reply", "EventBridge, Lambda, SageMaker blue/green update"],
        ["Monitoring", "Per-image statistics", "Five metrics and two alarms", "CloudWatch, EventBridge"],
    ])
    b.figure("fig3_2_release_flow.png", "Figure 3.2", "Path of a retraining request: guard, training, golden-set test, release rule, approval, blue/green update and rollback.")
    b.h3("3.3 Module Description")
    b.p("**Capture.** Clients send an image to an HTTPS address served by API Gateway. A Lambda function saves the image in the raw/ area of an S3 bucket, calls the SageMaker endpoint, and writes one row to the images table in DynamoDB. The row holds the file name, the model version, the number of detections, the highest confidence, the box area as a share of the image, the brightness and a blur score. The function replies with the boxes, their scores and the model version. If the endpoint is switched off, it replies with a clear 503 message. Files in raw/ are deleted after 30 days, which limits how long personal data is kept.")
    b.p("**Serving.** A SageMaker real-time endpoint on one ml.m5.large instance loads the OpenVINO form of the detector. A small handler resizes the image to 416 by 416 pixels, normalises its colours, runs the model and keeps the boxes whose score is at least 0.4. This threshold was chosen from the precision and recall measurements in Section 5.1. SageMaker endpoints cannot be paused, so two scripts delete and recreate the endpoint while keeping the model and its settings.")
    b.caption("Table 3.2", "Statistics stored for every image")
    b.table([2300, 3300, 3426], ["Statistic", "How it is measured", "What it reveals"], [
        ["Number of detections", "Boxes with a score of at least 0.4", "Empty scenes or missed plates"],
        ["Top confidence", "Highest score returned for the image", "How sure the model is"],
        ["Box area share", "Plate box area divided by image area", "Camera distance or zoom changes"],
        ["Brightness", "Mean grey level of the image", "Night or glare"],
        ["Blur score", "Variance of the Laplacian filter", "Focus problems or motion"],
    ], keep=True)
    b.p("**Automatic labelling.** When an image lands in raw/, S3 sends a message to an SQS queue, and a labeller Lambda function with a low concurrency limit picks it up, so that rate limits of the model service never lose an image. The function asks Amazon Nova 2 Lite, through the Bedrock Converse API, to find all licence plates and return tight boxes. Nova 2 Lite is reached through the Global inference profile, because the model is not offered in-Region in Sydney (AWS, 2026e). Nova returns boxes on a scale of 0 to 1000, which the function converts to pixels. The service reports a typical cost of about 5.69 dollars for 10,000 images (AWS, 2026d).")
    b.p("Nova is guided by a written prompt and is not trained on this task, so its boxes can be loose. Training on its output without checks would let errors build up, because a model would learn from its own mistakes (Xie et al., 2020). Table 3.3 lists the four rules that decide where each image goes.")
    b.caption("Table 3.3", "Agreement rules for automatic labels")
    b.table([2600, 3600, 2826], ["Case", "Rule", "Action"], [
        ["Nova and the live detector both find a plate and their boxes overlap with IoU of at least 0.5", "Boxes agree on position", "Accept the label and store it in labels/auto/"],
        ["Only Nova finds a plate", "Accept only if the box has a plausible plate shape and size; such labels are limited to about 30% of a training batch", "Accept within the limit, otherwise quarantine"],
        ["Only the live detector finds a plate, or the two boxes disagree on position", "The image is ambiguous", "Move to quarantine/ and keep out of training"],
        ["Neither finds a plate", "No label can be made", "Record as no plate; not used for training"],
    ], keep=True)
    b.p("**Retraining.** The retraining pipeline has five steps: prepare the dataset, train, evaluate, apply the release rule, and register the model. The prepare step gathers the labels made since the last version and mixes them with the original data in a 30 to 70 proportion. The training step runs as a SageMaker training job on an ml.m5.xlarge instance with a maximum run time of two hours. It starts from the previous checkpoint with a low learning rate and then exports the model to ONNX and to the OpenVINO form. A guard Lambda function starts the pipeline only if no run is active, which is enforced with a conditional write to DynamoDB, and only if at least 24 hours have passed since the last run.")
    b.p("**Triggers.** Four things can start a run: a weekly EventBridge schedule, a count of 200 new accepted labels, a drift alarm, and a manual request. All four call the guard, so that two triggers firing together still start only one run.")
    b.p("**Evaluation and release.** The evaluation step runs the candidate and the live model on the golden set and computes average precision at an overlap of 0.50, recall and CPU time with the COCO evaluation tool (Lin et al., 2014). A candidate is registered as pending approval only if its average precision is at least 0.01 above the live model and its recall is no worse. The metrics are attached to the registered version. Approving the version raises an EventBridge event that starts a deploy Lambda function. The function creates a new endpoint configuration and updates the endpoint with a blue/green deployment, in which SageMaker builds a new set of instances, shifts the traffic and keeps watching during a baking period. If a CloudWatch alarm on server errors or on 95th-percentile latency trips, all traffic returns to the old instances (AWS, 2026g).")
    b.p("**Monitoring.** The capture function publishes five custom metrics to CloudWatch: mean top confidence, share of images with no plate, mean brightness, mean blur and mean box size. SageMaker Model Monitor is not used for this, because its data-quality checks work on tabular data only (AWS, 2026j). One alarm fires when the mean top confidence over 100 images falls below 0.70. A second fires when the share of images with no plate exceeds 0.15, about twice the normal value. Missing data counts as not breaching, because traffic can be sparse. Alarm changes are sent through EventBridge to the guard.")
    b.p("**Guardrails.** An idle-shutdown Lambda function runs every 15 minutes and deletes the endpoint when CloudWatch shows no requests in the last 30 minutes. A budget alarm and a script that prints the remaining credits and days of the plan are used before and after every session. All resources except the endpoint are defined as code, and one command removes them.")
    b.h3("3.4 Algorithms / Models Used")
    b.p("Table 3.4 lists the models and rules that make up the intelligence of the system. The detector and the labeller are models. The rules turn their outputs into decisions.")
    b.caption("Table 3.4", "Models and decision rules")
    b.table([1900, 2500, 2800, 1826], ["Component", "Role", "Key settings", "Cost profile"], [
        ["PicoDet-XS detector", "Finds plate boxes and scores", "LCNet backbone (scale 0.35), 96-channel neck, 416 by 416 input, one class", "About 0.7 million parameters; CPU"],
        ["Amazon Nova 2 Lite", "Proposes boxes for stored images", "Plate-only prompt, boxes on a 0 to 1000 scale", "About 0.06 cent per image"],
        ["Agreement rules", "Accept or quarantine proposals", "IoU 0.5; at most about 30% Nova-only labels", "Negligible"],
        ["Release rule", "Allows or blocks a new model", "AP50 gain of at least 0.01; recall not lower", "One evaluation per run"],
        ["Drift rules", "Signal changing images", "Top confidence below 0.70; no-plate share above 0.15", "Five metrics per interval"],
    ])
    b.p("**The detector.** PicoDet-XS is an anchor-free, one-stage detector. The LCNet backbone extracts features at three scales, a path-aggregation neck called LCPAN mixes them, and the head predicts, for each location, a score and the distances to the four box edges. The model is trained with a loss that combines a classification term that weights the quality of each prediction, a box-overlap term and a distribution term for the edges (Yu et al., 2021). The result is small enough to run on two CPU threads.")
    b.p("**Overlap and scores.** A predicted box is compared with the true box by the intersection over union, written IoU. With TP, FP and FN the numbers of true positives, false positives and false negatives at a chosen score threshold, precision, recall and the F1 score are:")
    b.formula("IoU = area(A ∩ B) / area(A ∪ B)")
    b.formula("Precision = TP / (TP + FP)        Recall = TP / (TP + FN)")
    b.formula("F1 = 2 · Precision · Recall / (Precision + Recall)")
    b.p("Average precision (AP) is the area under the precision-recall curve obtained by lowering the score threshold from high to low. AP50 counts a prediction as correct when IoU is at least 0.50. AP50:95 averages the result over IoU thresholds from 0.50 to 0.95 in steps of 0.05 and is stricter, because it also rewards tightly fitting boxes (Lin et al., 2014).")
    b.caption("Table 3.5", "Notation for the evaluation measures")
    b.table([2000, 7026], ["Symbol", "Meaning"], [
        ["A, B", "Predicted box and true box"],
        ["IoU", "Overlap of two boxes: shared area divided by combined area"],
        ["TP, FP, FN", "Correct detections, wrong detections and missed plates at one score threshold"],
        ["AP50", "Average precision when a detection counts if IoU is at least 0.50"],
        ["AP50:95", "Average precision averaged over IoU thresholds 0.50 to 0.95"],
        ["Top confidence", "Highest score returned for one image; its mean over a window of images is the main drift signal"],
    ])
    b.p("**Why this detector suits the task.** Licence plates are small, usually one per image, and have a regular shape, so a compact detector is enough. In the training set the median plate covers 1.95% of the image and the median width-to-height ratio is 1.75. A small model also keeps serving cost low and allows retraining on a CPU instance, which matters because GPU instances may be blocked or have zero quota on a new account (AWS, 2026b).")


def ch4(b, stats):
    b.chapter(4, "SYSTEM IMPLEMENTATION")
    b.objective("To describe the environment, tools, implementation steps, dataset and key code of the system.")
    b.h3("4.1 Hardware and Software Specifications")
    b.p("Development and testing were carried out on a Windows laptop running Ubuntu under WSL2, and the cloud resources were created in an AWS account on the Free plan in the Asia Pacific (Sydney) Region. Table 4.1 lists the configuration.")
    b.caption("Table 4.1", "Hardware and software configuration")
    b.table([2600, 6426], ["Item", "Specification"], [
        ["Development machine", "Laptop with 16 logical processors and 15 GB of memory; Ubuntu on WSL2; Python 3.11"],
        ["AWS account and Region", "AWS Free plan (sign-up credit of 100 US dollars, plus up to 100 dollars more for completing activities, valid for 6 months); Asia Pacific (Sydney), ap-southeast-2"],
        ["Serving instance", "One ml.m5.large SageMaker real-time endpoint (2 virtual CPUs, 8 GiB memory)"],
        ["Training instance", "ml.m5.xlarge SageMaker training job (4 virtual CPUs, 16 GiB), maximum run time of 2 hours"],
        ["Training software", "PaddlePaddle 2.6.2 and PaddleDetection (PicoDet-XS configuration), scikit-learn 1.4-2 SageMaker container with Python 3.12 (AWS, 2026i)"],
        ["Serving software", "OpenVINO 2026.2.1, NumPy 1.26.4, OpenCV 4.11"],
        ["Evaluation software", "pycocotools 2.0.8, ONNX 1.17, ONNX Runtime 1.31, paddle2onnx 2.1"],
        ["Labelling model", "Amazon Nova 2 Lite through Amazon Bedrock (Global inference profile)"],
    ], bold_first=True)
    b.h3("4.2 Tools / Libraries Used")
    b.p("PaddleDetection supplies the PicoDet-XS model, the training loop and the export tools, and PaddlePaddle is the numerical library beneath it. OpenVINO converts the trained model to a form that runs quickly on ordinary Intel and AMD processors and is used for serving. ONNX is an open exchange format for models, and ONNX Runtime is used as a second, independent way to run it when checking results. OpenCV reads and resizes images and computes brightness and blur. NumPy handles the arrays, and pycocotools computes the standard COCO measures.")
    b.p("On the AWS side, the boto3 library lets the Lambda functions and scripts call AWS services. The AWS Cloud Development Kit in Python describes the infrastructure as code and produces CloudFormation templates. GitHub Actions runs code checks and unit tests on every change to the Lambda functions and the labelling rules. Label Studio on the development machine is available for correcting the golden set.")
    b.h3("4.3 Implementation Details")
    b.p("**Storage and tables.** One S3 bucket holds the prefixes raw/, labels/auto/, quarantine/, datasets/, golden/ and models/. Versioning is on, public access is blocked and a lifecycle rule expires raw/ after 30 days. The images table in DynamoDB holds one row per image with a time-to-live value, and the state table holds counters and the run lock. Every resource carries a project tag, and a budget alert warns when spending approaches the credit balance.")
    b.p("**Model package and endpoint.** The OpenVINO files of the current model, together with a small handler script and its requirements file, are packed into one archive in models/. A script creates the SageMaker model, the endpoint configuration and the endpoint on a prebuilt Python container, and a second script deletes only the endpoint. The handler follows the standard four SageMaker functions: load the model, decode the request, predict and format the answer. ONNX Runtime is not used for serving, because the ONNX file fails in it when exactly one box survives non-maximum suppression (4 of 150 golden images, Section 5.2), whereas the OpenVINO model returns the same boxes without errors.")
    b.p("**Capture interface.** An HTTP API in API Gateway forwards each request to the capture Lambda function. The function computes the five statistics with NumPy and OpenCV, writes the row and returns the answer together with the model version, so that anyone can see which model replied.")
    b.p("**Labelling.** An S3 event on raw/ feeds the SQS queue. The labeller function applies the prompt and the four rules of Table 3.3, writes accepted labels to labels/auto/ and the rest to quarantine/, updates the image row and increases the new-label counter in the state table.")
    b.p("**Training and evaluation.** The training script reads a folder of images and a COCO-format annotation file, mixes original and new data in a 70 to 30 proportion, fine-tunes from the previous checkpoint and exports the result. The evaluation script runs the models on the golden set and writes an evaluation file with average precision, recall and latency for both models. The evaluation script and the dataset tools also run unchanged on the development machine, which is how they were tested before they were used in the pipeline.")
    b.p("**Release and monitoring.** Table 4.2 lists the deployment steps in the order in which they were carried out.")
    b.caption("Table 4.2", "Deployment steps on AWS")
    b.table([800, 2400, 5826], ["Step", "Action", "Detail"], [
        ["1", "Account and quotas", "Sign up on the Free plan and note the Region; confirm quotas of at least 1 for ml.m5.large endpoints and ml.m5.xlarge training; enable Amazon Nova 2 Lite in Bedrock"],
        ["2", "Storage", "Create the S3 bucket, its prefixes and lifecycle rule; create the DynamoDB tables; set the budget alert"],
        ["3", "Model package", "Pack the OpenVINO files and handler, upload to models/, create the SageMaker model and endpoint configuration"],
        ["4", "Capture interface", "Deploy the capture Lambda function behind an HTTP API; test with sample images"],
        ["5", "Labeller", "Connect S3 events to SQS and the labeller function; check the rules on the golden set"],
        ["6", "Pipeline and triggers", "Create the five-step SageMaker Pipeline, the guard function and the four triggers"],
        ["7", "Release and alarms", "Create the Model Registry group, the deploy function, the two drift alarms and the rollback alarms"],
        ["8", "Guardrails and teardown", "Deploy the idle-shutdown function and the credit-check script; keep one command that removes the stack"],
    ])
    b.h3("4.4 Dataset Collection and Descriptions")
    t, v, s2, g = stats["train"], stats["val"], stats["train_2k"], stats["golden"]
    b.p(f"The detector data are a merged collection of public, annotated licence plate images with one class, license_plate. Several file names carry the export marks of an annotation platform, and about 83% of the images are 416 by 416 pixels. A conversion script turned the original annotation table into COCO files, split 90% to 10% at random with a fixed seed of 42. The training set has {t['images']:,} images and {t['boxes']:,} boxes. The validation set has {v['images']:,} images and {v['boxes']:,} boxes. Table 4.3 gives the sets, and Table 4.4 summarises their statistics.")
    b.caption("Table 4.3", "Image sets used in the project")
    b.table([2300, 1100, 5626], ["Set", "Images", "Purpose"], [
        ["Training set", f"{t['images']:,}", "Original data for retraining; mixed with new labels at 70%"],
        ["Training subset", f"{s2['images']:,}", "Random part of the training set used to train the first model"],
        ["Validation set", f"{v['images']:,}", "Random 10% split used for the first accuracy check"],
        ["Held-out sources", "681", "Validation images whose source picture does not appear in the training set"],
        ["Golden set", f"{g['images']}", "150 images drawn at random (seed 42) from the held-out sources; never used for training; the release gate"],
    ], aligns=["left", "center", "left"], bold_first=True)
    b.caption("Table 4.4", "Dataset statistics")
    def r(k, name): d = stats[k]; return [name, f"{d['images']:,}", f"{d['boxes']:,}", f"{d['boxes_per_image']:.2f}", f"{d['median_rel_area']*100:.2f}%", f"{d['median_aspect']:.2f}", f"{d['share_416']*100:.0f}%"]
    b.table([2200, 1050, 1050, 1150, 1500, 1076, 1000], ["Set", "Images", "Boxes", "Boxes per image", "Median plate area share", "Median width / height", "Size 416 by 416"],
            [r("train", "Training set"), r("train_2k", "Training subset"), r("val", "Validation set"), r("golden", "Golden set")], aligns=["left"] + ["center"] * 6, bold_first=True)
    b.p("**Source overlap.** Filenames of the form name_jpg.rf.hash show that the collection contains several augmented copies of the same source photograph. Because the split was random, 1,865 of the 2,546 validation images (73%) share a source name with a training image. The 681 images whose source does not appear in the training set form the held-out sources, and the golden set is drawn from them. The golden plates are smaller than the average: their median area share is 0.49%, against 1.95% in the training set.")
    b.p("**Plate size and shape.** Figure 4.1 shows the sizes of the image sets and the distribution of the plate area. Most plates cover between 0.5% and 6% of the image, so the detector has to find objects that fill only a small part of the picture. Figure 4.2 shows that 93% of training images contain exactly one plate and that the width is typically 1.5 to 2.5 times the height.")
    b.figure("fig4_1_dataset.png", "Figure 4.1", "Image sets (left) and plate area as a share of the image (right, logarithmic scale).")
    b.figure("fig4_2_boxstats.png", "Figure 4.2", "Plates per image (left) and plate width divided by height (right) in the training set.")
    b.h3("4.5 Pseudocode / Code Snippets")
    b.p("The excerpts below are the core of the implementation. The first is the serving routine: it prepares an image, runs the OpenVINO model and keeps the boxes above the score threshold.")
    b.code([
        "def detect(image_bgr, threshold=0.4):",
        "    h, w = image_bgr.shape[:2]",
        "    x = cv2.resize(image_bgr, (416, 416), interpolation=cv2.INTER_CUBIC)",
        "    x = (x[:, :, ::-1].astype('float32') / 255 - MEAN) / STD      # RGB, ImageNet statistics",
        "    x = x.transpose(2, 0, 1)[None]",
        "    scale = np.array([[416 / h, 416 / w]], dtype='float32')",
        "    out = model({'image': x, 'scale_factor': scale})",
        "    rows = out[0][: int(out[1][0])]            # class, score, x1, y1, x2, y2",
        "    return [r for r in rows if r[1] >= threshold]",
    ])
    b.p("The labeller applies the agreement rules of Table 3.3 to the boxes of the live detector and of Nova 2 Lite.")
    b.code([
        "def decide(live, nova, nova_only_left):",
        "    for box in nova:",
        "        if any(iou(box, d) >= 0.5 for d in live):",
        "            return 'accept', box",
        "        if not live and plausible_plate(box) and nova_only_left > 0:",
        "            return 'accept', box           # Nova-only, limited to about 30% of a batch",
        "    if live or nova:",
        "        return 'quarantine', None",
        "    return 'no_plate', None",
    ])
    b.p("The guard function starts a pipeline run only if the run lock can be taken and the last run is at least 24 hours old.")
    b.code([
        "def lambda_handler(event, context):",
        "    now = int(time.time())",
        "    try:",
        "        state.update_item(Key={'pk': 'pipeline'},",
        "            UpdateExpression='SET running = :t, started = :now',",
        "            ConditionExpression='attribute_not_exists(running) OR (running = :f AND last_end < :cutoff)',",
        "            ExpressionAttributeValues={':t': True, ':f': False, ':now': now, ':cutoff': now - 86400})",
        "    except ClientError as e:",
        "        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':",
        "            return {'started': False, 'reason': 'busy or too soon'}",
        "        raise",
        "    sagemaker.start_pipeline_execution(PipelineName='plate-detector-retrain')",
        "    return {'started': True}",
    ])
    b.p("The release rule is a single comparison of the evaluation files of the candidate and the live model.")
    b.code([
        "def passes_gate(new, live):",
        "    return new['ap50'] >= live['ap50'] + 0.01 and new['recall'] >= live['recall']",
    ])


def ch5(b, E):
    b.chapter(5, "RESULTS and DISCUSSION")
    b.objective("To present the measured results of the detector, the drift signals and the serving cost, to compare the model formats, and to interpret the findings.")
    b.h3("5.1 Experimental Results")
    fv, cl, lk, hs = E["e1"]["full_val"], E["e1"]["clean_holdout"], E["e1"]["leaky_val"], E["e1"]["clean_vs_2k_subset"]
    gold = E["e3"]["brightness"][0]
    b.p(f"The first detector was trained on a 2,000-image subset and then evaluated with the standard COCO measures. Table 5.1 reports the results on the sets of Section 4.4. On the full validation set of 2,546 images the average precision at IoU 0.50 is {fv['AP50']:.3f} and the stricter AP50:95 is {fv['AP']:.3f}. The same figures were obtained both with the PaddleDetection evaluation tool and with the OpenVINO model used for serving, which confirms that the conversion did not change the results.")
    b.caption("Table 5.1", "Detector accuracy by evaluation set")
    b.table([3600, 1100, 1400, 1500, 1426], ["Evaluation set", "Images", "AP50", "AP50:95", "Recall (AR@100)"], [
        ["Full validation set", f"{fv['n']:,}", f"{fv['AP50']:.3f}", f"{fv['AP']:.3f}", f"{fv['AR']:.3f}"],
        ["Images whose source is not in the 2,000-image subset", f"{hs['n']:,}", f"{hs['AP50']:.3f}", f"{hs['AP']:.3f}", f"{hs['AR']:.3f}"],
        ["Images sharing a source with the training set", f"{lk['n']:,}", f"{lk['AP50']:.3f}", f"{lk['AP']:.3f}", f"{lk['AR']:.3f}"],
        ["Held-out sources (not in the training set)", f"{cl['n']:,}", f"{cl['AP50']:.3f}", f"{cl['AP']:.3f}", f"{cl['AR']:.3f}"],
        ["Golden set (drawn from held-out sources)", "150", f"{gold['ap50']:.3f}", f"{gold['ap']:.3f}", "-"],
    ], aligns=["left", "center", "center", "center", "center"])
    b.figure("fig5_2_accuracy.png", "Figure 5.1", "Detector accuracy by evaluation set: average precision at IoU 0.50 and averaged over IoU 0.50 to 0.95.")
    b.p("The score depends strongly on which images are used. Images that share a source picture with training data are easy, and the detector reaches an AP50 of 0.986 on them. On the 681 held-out sources it reaches 0.768, and on the golden set 0.761. The held-out figure is therefore the honest estimate of how the model behaves on a new source, and it is the reference used by the release rule.")
    b.p("**Choice of the score threshold.** The detector returns up to 100 boxes per image, each with a score, and the serving code must decide which to keep. Table 5.2 shows precision, recall and F1 on the held-out sources for several thresholds, and Figure 5.2 plots them. The F1 score is highest, at about 0.79, between thresholds of 0.4 and 0.5. A threshold of 0.4 was chosen because it keeps more plates than 0.5 (recall of 71.7% against 68.4%) while precision stays close to 87%.")
    b.caption("Table 5.2", "Precision, recall and F1 by score threshold (held-out sources)")
    rows = []
    for r in E["e1"]["pr_curve"]:
        if r["thr"] in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
            rows.append([f"{r['thr']:.1f}", f"{r['p']:.3f}", f"{r['r']:.3f}", f"{r['f1']:.3f}"])
    b.table([2200, 2275, 2275, 2276], ["Score threshold", "Precision", "Recall", "F1 score"], rows, aligns=["center"] * 4)
    b.figure("fig5_1_pr.png", "Figure 5.2", "Precision against recall (left) and effect of the score threshold (right) on the held-out sources.")
    b.h3("5.2 Performance Comparison / Benchmarks")
    ov, ort = E["e2"]["openvino_2threads"], E["e2"]["onnxruntime_2threads"]
    sz = E["e2"]["sizes_mb"]
    b.p(f"Table 5.3 compares the three forms of the model. The timings were measured on the 150 golden images with two CPU threads, which matches the two virtual CPUs of the ml.m5.large serving instance. The OpenVINO model needs a median of {ov['inference_ms']['median']:.1f} ms for the model and {ov['total_ms']['median']:.1f} ms including image preparation, with a 95th percentile of {ov['total_ms']['p95']:.1f} ms. ONNX Runtime needs {ort['inference_ms']['median']:.1f} ms for the model alone, and it stopped with an error on {ort['failures']} of {ort['n']} images, those where exactly one box remained after non-maximum suppression. For this reason OpenVINO is the format served.")
    b.caption("Table 5.3", "Comparison of the model formats on two CPU threads")
    b.table([2300, 1500, 1700, 1700, 1826], ["Format", "Size (MB)", "Median time per image (ms)", "95th percentile (ms)", "Errors on 150 images"], [
        ["Training checkpoint", f"{sz['checkpoint']:.2f}", "-", "-", "-"],
        ["ONNX with ONNX Runtime", f"{sz['onnx']:.2f}", f"{ort['inference_ms']['median'] + ov['preprocess_ms']['median']:.1f}", f"{ort['inference_ms']['p95'] + ov['preprocess_ms']['p95']:.1f}", f"{ort['failures']}"],
        ["OpenVINO (served)", f"{sz['openvino']:.2f}", f"{ov['total_ms']['median']:.1f}", f"{ov['total_ms']['p95']:.1f}", "0"],
    ], aligns=["left", "center", "center", "center", "center"], bold_first=True)
    b.figure("fig5_4_latency.png", "Figure 5.3", "Time to process one image (left) and size of each model file (right).")
    b.p("Table 5.4 lists the operational checks used to confirm that each part of the system responds correctly, with the response each one should give.")
    b.caption("Table 5.4", "Operational checks")
    b.table([700, 2300, 3300, 2726], ["Check", "Action", "Expected response", "Component"], [
        ["C-01", "Send a clear image of a car", "HTTP 200 with plate boxes, scores and the model version; image and row appear in S3 and DynamoDB", "Capture, endpoint"],
        ["C-02", "Send an image while the endpoint is deleted", "HTTP 503 with a clear message; nothing is stored as a result", "Capture"],
        ["C-03", "Delete and recreate the endpoint with the scripts", "Service resumes with the same model and settings", "Scripts"],
        ["C-04", "Upload 50 images", "Rows and labels appear; accepted, quarantined and no-plate counts add up to 50", "Labeller"],
        ["C-05", "Fire two triggers at once", "Exactly one pipeline run starts", "Guard"],
        ["C-06", "Send 100 darkened or blurred images", "Mean top confidence falls below 0.70 and the alarm starts one run", "Monitoring, guard"],
        ["C-07", "Approve a version that is worse than the live model", "Not registered; the live model stays", "Release rule"],
        ["C-08", "Deploy a deliberately broken model", "Alarm trips and the endpoint returns to the previous version", "Blue/green update"],
        ["C-09", "Leave the endpoint idle for 30 minutes", "Idle-shutdown function deletes it", "Guardrails"],
    ], aligns=["center", "left", "left", "left"])
    b.h3("5.3 Visualization of Results (Graphs, Charts, Tables)")
    b.p("**Drift signals.** The golden images were darkened, blurred and covered with noise at increasing strengths, and the detector and the monitoring statistics were recorded at each level. Figure 5.4 shows that accuracy and the two drift signals move together: as the images degrade, AP50 falls, the mean top confidence falls and the share of images with no plate found rises. Table 5.5 gives the values at the stronger levels and shows whether the alarm rule of Section 3.3 would fire.")
    b.figure("fig5_3_drift.png", "Figure 5.4", "AP50 (top row) and drift signals (bottom row) as images become darker, blurrier or noisier; the dashed line is the alarm level of 0.70.")
    b.caption("Table 5.5", "Drift signals at increasing degradation (golden set)")
    rows = []
    def add(fam, label, lv):
        for r in E["e3"][fam]:
            if r["level"] in lv:
                fire = "Yes" if (r["mean_top_conf"] < 0.70 or r["no_det_rate"] > 0.15) else "No"
                rows.append([label.format(r["level"]), f"{r['ap50']:.3f}", f"{r['mean_top_conf']:.3f}", f"{r['no_det_rate']*100:.1f}%", fire])
    add("brightness", "Brightness factor {}", ["1.0", "0.25", "0.15", "0.10"])
    add("blur", "Blur sigma {}", ["2", "3", "4", "6"])
    add("noise", "Noise sigma {}", ["20", "35", "50", "70"])
    b.table([2700, 1400, 1700, 1700, 1526], ["Condition", "AP50", "Mean top confidence", "Images with no plate", "Alarm fires"], rows, aligns=["left"] + ["center"] * 4)
    b.p("The alarm stays silent for light changes and fires when accuracy has already dropped noticeably: at a brightness factor of 0.15, a blur of 3 pixels or noise of 35 grey levels, where AP50 is 0.68, 0.66 and 0.68 against 0.76 for the original images. The brightness curve is flat down to a factor of 0.35 and then falls, which shows that the detector tolerates ordinary dimming and is troubled only by very dark scenes. Blur and noise reduce accuracy more steadily.")
    b.p("**Cost.** Figure 5.5 and Table 5.6 give the estimated cost of the system. The endpoint is the largest item, and it is priced at the higher ml.m5.xlarge rate of 0.23 dollars an hour to leave a safe margin. The labelling cost uses the AWS estimate of 5.69 dollars per 10,000 images (AWS, 2026d, 2026f). The total is about 26 dollars, a quarter of the 100 dollars given at sign-up. Because endpoints cannot be paused, a forgotten ml.m5.xlarge endpoint would cost about 168 dollars a month, which is why the idle-shutdown function and the end-of-session script are part of the system.")
    b.caption("Table 5.6", "Estimated cost of the system")
    b.table([2800, 4400, 1826], ["Item", "Basis", "Estimate (US dollars)"], [
        ["Endpoint", "60 session-hours at the ml.m5.xlarge rate", "13.80"],
        ["Training", "6 runs of 2 hours on ml.m5.xlarge", "2.76"],
        ["Data preparation and evaluation", "10 hours on ml.m5.xlarge", "2.30"],
        ["Automatic labelling", "3,000 images through Nova 2 Lite", "1.71"],
        ["Lambda, API Gateway, S3, DynamoDB, SQS, CloudWatch, ECR", "Low volume", "about 5.00"],
        ["**Total**", "", "**about 26**"],
    ], aligns=["left", "left", "center"])
    b.figure("fig5_5_cost.png", "Figure 5.5", "Estimated cost by item, in US dollars.")
    b.h3("5.4 Interpretation and Analysis")
    b.p("**Why the score depends on the image source.** The first accuracy check gave an AP50 of 0.923, which looks excellent. The source analysis showed that three quarters of the validation images are augmented copies of training pictures, and the score on those is 0.986. On sources the model has never seen, the AP50 is 0.768. Without this check, the release rule would have compared models against a flattering number. This is why the golden set is drawn only from held-out sources and why the retraining data never include it.")
    b.p("**Small plates are the main difficulty.** The golden plates cover a median of 0.49% of the image, against 1.95% in the training set. Small objects are harder for any detector at 416 by 416 pixels, and this explains part of the gap between the golden set and the full validation set. Retraining on images from the real cameras, which the loop collects and labels, is the natural remedy.")
    b.p("**The threshold is a trade, not a constant.** Raising the threshold from 0.3 to 0.5 raises precision from 78.5% to 92.7% and lowers recall from 74.8% to 68.4%. A parking gate that is annoyed by false alarms may choose 0.5, while an enforcement camera that cannot afford a miss may choose 0.3. The value is kept in the configuration file, so an operator can change it without retraining.")
    b.p("**Confidence is a useful early warning.** The mean top confidence is cheap to compute, needs no labels, and moved in step with accuracy in every test. It does not say why the images changed, so the brightness, blur and box-size metrics are published beside it to help find the cause.")
    b.p("**Operational findings.** The OpenVINO model is smaller than the training checkpoint (1.77 MB against 2.85 MB) and about 33% faster than the ONNX file under ONNX Runtime. The ONNX file also fails on some images, which shows the value of testing each export form on real images before choosing a serving format. The labelling stage depends on a third-party model whose published end-of-life date is no sooner than 2 December 2026 (AWS, 2026e), so the model identifier is held in the configuration file and the prompt is tested again whenever it is changed.")
    b.p("**Limits of the evidence.** The accuracy figures come from a single detector trained on a 2,000-image subset, and the golden set contains only 150 images, so differences of a few points between two models on it are within normal variation. The timings come from one CPU configuration. The drift tests use synthetic darkening, blur and noise, which are simple stand-ins for real changes such as rain, glare and a new camera position. The Free plan lasts six months and ends the account afterwards, so the code, models and results are exported before it expires (AWS, 2026a).")


def ch6(b):
    b.chapter(6, "CONCLUSION and FUTURE WORK")
    b.p("This chapter summarises what the project achieved, states its main limitation, and outlines how the system can be extended.")
    b.h3("6.1 Conclusion")
    b.p("The project built and operates a closed loop that keeps a licence plate detector current on AWS. It covers capture, serving, automatic labelling, retraining, testing, release and monitoring, uses only services of the Free plan, and costs an estimated 26 US dollars. The main achievements are:")
    for t in [
        "**A working detector service.** A PicoDet-XS model of 1.8 MB serves plate boxes from a single ml.m5.large endpoint in about 17 ms per image on two CPU threads.",
        "**Trustworthy automatic labels.** Four agreement rules decide which Nova 2 Lite proposals become training labels, so that the detector does not learn from its own mistakes.",
        "**A release that cannot make things worse by accident.** A new model must beat the live model on a golden set of unseen sources before it is registered, and a blue/green update rolls back by itself if an alarm trips.",
        "**Early warning and low cost.** Five simple statistics and two alarms signal changing images, and an idle-shutdown function, a credit script and a one-command teardown keep the cost small.",
    ]:
        b.bullet(t)
    b.p("The detector reaches an AP50 of 0.923 on the full validation set, 0.768 on sources that never appear in training and 0.761 on the golden set. At the chosen score threshold of 0.4 it finds 71.7% of plates on held-out sources with a precision of 87.4%. These results show that a very small model, kept current by an automatic loop, is a practical basis for plate reading on inexpensive hardware.")
    b.p("**Lessons learned.** Several small decisions proved important. Separating validation images by source picture changed the picture of accuracy more than any model setting. Testing every export format on real images revealed an error that a single test image had hidden. Keeping the model name, the threshold, the schedule and the Region in one configuration file made each of them a one-line change. Putting every costly resource behind a script that removes it removed the main financial risk.")
    b.p("**Current technical constraints and limitations.** The detector finds plates but does not read their characters. It was trained on a limited set of public images, and its accuracy on small plates is lower than on large ones. The labelling stage relies on a general model from a third party that has a published end-of-life date. The Free plan lasts six months, and a golden set of 150 images gives only a coarse view of small differences between models. The system serves still images, not video streams.")
    b.h3("6.2 Future Work")
    b.p("Table 6.1 lists the enhancements in order of priority, with the technology that would be used and the outcome expected.")
    b.caption("Table 6.1", "Future enhancements")
    b.table([2500, 2500, 2826, 1200], ["Enhancement", "Technology", "Outcome", "Priority"], [
        ["Read the plate characters", "A text recognition model after the detector", "Complete plate recognition", "High"],
        ["Larger golden set from real cameras", "Label Studio and the quarantine queue", "Finer comparison between models", "High"],
        ["Human review of quarantined images", "A simple review page on S3 and API Gateway", "More accepted labels; safer retraining", "High"],
        ["Replacement of the labelling model", "A newer Nova or another Bedrock model, tested on the golden set", "Continuity after model retirement", "Medium"],
        ["Video streams", "Frame sampling and tracking before the detector", "Fewer duplicate images; real-time use", "Medium"],
        ["Faster retraining", "GPU training instances where quota allows", "Shorter runs; larger models", "Low"],
        ["Serving in several Regions", "Multi-Region endpoints and replicated buckets", "Lower delay and higher availability", "Low"],
    ], aligns=["left", "left", "left", "center"])
    b.p("Beyond these items, the system can be extended with privacy features such as blurring plates in stored images, with a dashboard of the drift metrics for operators, and with checks on how the detector performs separately for night, rain and motorcycles.")
