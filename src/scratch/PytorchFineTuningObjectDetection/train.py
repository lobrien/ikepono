import torch
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.models.detection.mask_rcnn import MaskRCNNPredictor
import torchvision
from torchvision.models.detection import FasterRCNN
from torchvision.models.detection.rpn import AnchorGenerator
import mlflow

from torchvision.transforms import v2 as T
import utils
from PennFudanDataset import PennFudanDataset
from engine import train_one_epoch, evaluate
from twilio.rest import Client

def get_model_instance_segmentation(num_classes):
    # load an instance segmentation model pre-trained on COCO
    model = torchvision.models.detection.maskrcnn_resnet50_fpn(weights="DEFAULT")

    # get number of input features for the classifier
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    # replace the pre-trained head with a new one
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)

    # now get the number of input features for the mask classifier
    in_features_mask = model.roi_heads.mask_predictor.conv5_mask.in_channels
    hidden_layer = 256
    # and replace the mask predictor with a new one
    model.roi_heads.mask_predictor = MaskRCNNPredictor(
        in_features_mask,
        hidden_layer,
        num_classes
    )

    return model

def get_transform(train):
    transforms = []
    if train:
        transforms.append(T.RandomHorizontalFlip(0.5))
    transforms.append(T.ToDtype(torch.float, scale=True))
    transforms.append(T.ToPureTensor())
    return T.Compose(transforms)

def main():
    try:
        # train on the GPU or on the CPU, if a GPU is not available
        device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

        # our dataset has two classes only - background and person
        num_classes = 2
        # use our dataset and defined transformations
        dataset = PennFudanDataset('../../../data/PennFudanPed', get_transform(train=True))
        dataset_test = PennFudanDataset('../../../data/PennFudanPed', get_transform(train=False))

        # split the dataset in train and test set
        indices = torch.randperm(len(dataset)).tolist()
        dataset = torch.utils.data.Subset(dataset, indices[:-50])
        dataset_test = torch.utils.data.Subset(dataset_test, indices[-50:])

        # define training and validation data loaders
        data_loader = torch.utils.data.DataLoader(
            dataset,
            batch_size=8,
            shuffle=True,
            collate_fn=utils.collate_fn
        )

        data_loader_test = torch.utils.data.DataLoader(
            dataset_test,
            batch_size=1,
            shuffle=False,
            collate_fn=utils.collate_fn
        )

        # get the model using our helper function
        model = get_model_instance_segmentation(num_classes)

        # move model to the right device
        model.to(device)

        # construct an optimizer
        params = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.SGD(
            params,
            lr=0.005,
            momentum=0.9,
            weight_decay=0.0005
        )

        # and a learning rate scheduler
        lr_scheduler = torch.optim.lr_scheduler.StepLR(
            optimizer,
            step_size=3,
            gamma=0.1
        )

        # let's train it just for 2 epochs
        num_epochs = 30

        with mlflow.start_run():
            mlflow.log_param("device", device)
            mlflow.log_param("model", "maskrcnn_resnet50_fpn")
            mlflow.log_param("num_epochs", num_epochs)
            mlflow.log_param("lr", 0.005)
            mlflow.log_param("momentum", 0.9)
            mlflow.log_param("weight_decay", 0.0005)
            mlflow.log_param("step_size", 3)
            mlflow.log_param("gamma", 0.1)

            for epoch in range(num_epochs):
                # train for one epoch, printing every 10 iterations
                train_one_epoch(model, optimizer, data_loader, device, epoch, print_freq=1)
                # update the learning rate
                lr_scheduler.step()
                # evaluate on the test dataset
                evaluate(model, data_loader_test, epoch=epoch, device=device)
    finally:
        print("That's it!")
        sid = os.environ['twilio_sid']
        token = os.environ['twilio_token']
        to_phone = os.environ['larry_phone']
        twilio_phone = os.environ['twilio_phone']
        client = Client(sid, token)
        message = client.messages.create(to=to_phone, from_=twilio_phone, body="Training complete")


if __name__ == "__main__":
    main()