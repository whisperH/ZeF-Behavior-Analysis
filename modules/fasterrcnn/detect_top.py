import os, sys

sys.path.append(".")
import torch
import argparse
import datetime
from torchvision import models
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.transforms import functional as F
import time
from common.utility import *
import pandas as pd
import matplotlib.pyplot as plt


def initializeModel(pretrained, num_classes):
    """
    Loads the Faster RCNN ResNet50 model from torchvision, and sets whether it is COCO pretrained, and adjustes the heds box predictor to our number of classes.

    Input:
        pretrained: Whether to use a CoCo pretrained model
        num_classes: How many classes we have:

    Output:
        model: THe initialized PyTorch model
    """

    # Load model
    model = models.detection.fasterrcnn_resnet50_fpn(pretrained=pretrained, pretrained_backbone=pretrained)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)

    return model


@torch.no_grad()
def inference(args):
    VideoName = args["VideoName"]
    vidPath = os.path.join(args["video_path"], VideoName)
    camId = args["camId"]
    camNO = VideoName.split(".")[0].split("_")[-1]
    show = args["show"]
    outputPath = os.path.join(args["outputPath"])
    startFrame = args["startFrame"]
    endFrame = args["endFrame"]
    config_folder = args["config_path"]
    region_name = args["region_name"]

    Exp_region_pos = load_EXP_region_pos_setting(config_folder, camNO)
    if Exp_region_pos is None:
        return

    region_area = Exp_region_pos[region_name]

    # model_path_root = '/home/huangjinze/code/3D-ZeF/'
    model_path_root = args["weights_root"]
    if camId == '1':
        threshold = 0.02
        weight_path = os.path.join(model_path_root, '2021_09_23-10_07_58/models/faster_RCNN_resnet50_1_top_epochs.tar')
    else:
        threshold = 0.001
        weight_path = os.path.join(model_path_root, '2021_09_22-13_17_44/models/faster_RCNN_resnet50_1_front_epochs.tar')

    if not os.path.isdir(outputPath):
        os.makedirs(outputPath)

    # train on the GPU or on the CPU, if a GPU is not available
    if torch.cuda.is_available():
        device = torch.device('cuda')
        print("Using GPU")
    else:
        print("WARNING: Using CPU")
        device = torch.device('cpu')

    # our dataset has two classes only - background and zebrafish
    num_classes = 2

    model = initializeModel(False, num_classes)
    model.load_state_dict(torch.load(weight_path, map_location=device)["model_state_dict"])

    cpu_device = torch.device("cpu")

    cap = cv2.VideoCapture(vidPath)

    if not cap.isOpened():
        print("VIDEO NOT FOUND: {}".format(vidPath))

    # move model to the device (GPU/CPU)
    model.to(device)
    model.eval()

    id_map = {0: "Background", 1: "Zebrafish"}
    output_df = pd.DataFrame(
        columns=["Filename", "Object ID", "Annotation tag", "Upper left corner X", "Upper left corner Y",
                 "Lower right corner X", "Lower right corner Y", "Confidence", "Time_string"])

    frameCount = 0
    while (cap.isOpened()):
        ret, img = cap.read()
        if img is None:
            break

        frameCount += 1

        # if frameCount % 1000 == 0:
        print(f"{frameCount} in {VideoName}")

        if frameCount < startFrame:
            continue

        if (frameCount > endFrame) and (endFrame > 0):
            frameCount -= 1
            break

        if ret:
            show_img = img.copy()

            # 在这里设置图片区域
            tl_x, tl_y, br_x, br_y = region_area
            img[0:tl_y, :] = 0
            img[:, 0:tl_x] = 0
            img[br_y:, :] = 0
            img[:, br_x:] = 0

            # ###########################################

            img = F.to_tensor(img)
            img = [img.to(device)]

            outputs = model(img)
            outputs = {k: v.to(cpu_device) for k, v in outputs[0].items()}

            bboxes = outputs["boxes"].cpu().detach().numpy()
            labels = outputs["labels"].cpu().detach().numpy()
            scores = outputs["scores"].cpu().detach().numpy()
            filename = str(frameCount).zfill(6) + ".jpg"

            output_dict = {"Filename": [filename] * len(scores),
                           "Frame": [frameCount] * len(scores),
                           "Object ID": [-1] * len(scores),
                           "Annotation tag": [id_map[x] for x in labels],
                           "Upper left corner X": list(bboxes[:, 0]),
                           "Upper left corner Y": list(bboxes[:, 1]),
                           "Lower right corner X": list(bboxes[:, 2]),
                           "Lower right corner Y": list(bboxes[:, 3]),
                           "Confidence": list(scores)}
            output_df = pd.concat([output_df, pd.DataFrame.from_dict(output_dict)], ignore_index=True)

            if show:

                for ib, iscore in zip(bboxes, scores):
                    if iscore >= threshold:
                        cv2.rectangle(show_img, (int(ib[0]), int(ib[1])), (int(ib[2]), int(ib[3])), (0, 255, 0), 2)
                # print("=======================")
                try:
                    cv2.imshow(f'demo', show_img)
                    # cv2.namedWindow(f'demo{frameCount}', 0)
                    # cv2.resizeWindow(f'demo{frameCount}', 676, 380)
                    # cv2.imshow(f'demo{frameCount}', show_img)
                    cv2.waitKey(100)
                    # cv2.destroyWindow(f'demo{frameCount}')
                except:
                    plt.imshow(show_img)
                    plt.show()

                # plt.imshow(show_img)
                # plt.show()
        else:
            break
    output_df.to_csv(os.path.join(outputPath, VideoName.replace(".avi", ".csv")), index=False, sep=",")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    # ap.add_argument("-f", "--root_path", default="/home/data/HJZ/zef/exp_pre",
    # ap.add_argument("-f", "--video_path", default="E:\\data\\3D_pre\\D7_T4\\cut_video",
    ap.add_argument("-f", "--video_path", default="E:\\data\\OCU_ZeF\\cut_video",
                    help="Path to folder")

    # ap.add_argument('--config_path', type=str, default='/home/data/HJZ/zef/exp_pre/', help='config path')
    ap.add_argument('--config_path', type=str, default='E:\\data\\OCU_ZeF', help='config path')

    ap.add_argument("-vn", "--VideoName",
                    # default='2021_09_18_19_51_20_D01.avi')
                    default='20211027_ch12.MOV')
    ap.add_argument("-o", "--outputPath", default="E:\\data\\OCU_ZeF/processed/")
    ap.add_argument("-r", "--region_name", default="1_Mutant")

    ap.add_argument("-c", "--camId",
                    # default='1',
                    default='2',
                    help="Camera ID. top = 1 and left = 2，right = 3")
    ap.add_argument("-gpu", "--gpustr", default="0")

    ap.add_argument("-w", "--weights_root",
                    default='E:\\code/3D-ZeF/modules/Sessions/',
                    # default='/home/huangjinze/code/3D-ZeF/modules/Sessions/',
                    help="Path to the trained model weights")
    ap.add_argument("-sf", "--startFrame", default=0, type=int)
    ap.add_argument("-ef", "--endFrame", default=1850, type=int)
    # ap.add_argument("-o", "--outputPath", default="/home/data/HJZ/zef/exp_pre/processed")
    ap.add_argument("-v", "--show", default=True, action='store_true', help="Show video")

    args = vars(ap.parse_args())

    gpu_str = args['gpustr']
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_str

    inference(args)
