# Modified track.py with sitting duration tracking and timestamp logging

import argparse
import cv2
import numpy as np
from functools import partial
from pathlib import Path
from datetime import datetime
import pandas as pd
import torch

from boxmot import TRACKERS
from boxmot.tracker_zoo import create_tracker
from boxmot.utils import ROOT, WEIGHTS, TRACKER_CONFIGS
from boxmot.utils.checks import RequirementsChecker
from tracking.detectors import (get_yolo_inferer, default_imgsz,
                                is_ultralytics_model, is_yolox_model)

checker = RequirementsChecker()
checker.check_packages(('ultralytics @ git+https://github.com/mikel-brostrom/ultralytics.git', ))

from ultralytics import YOLO
from ultralytics.utils.plotting import Annotator, colors
from ultralytics.data.utils import VID_FORMATS
from ultralytics.utils.plotting import save_one_box

sitting_log = {}  # {track_id: {'start': datetime}}
csv_output = []   # list of [Person ID, Start Time, End Time, Duration]

def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    if interArea == 0:
        return 0.0

    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return interArea / float(boxAArea + boxBArea - interArea)

def on_predict_start(predictor, persist=False):
    assert predictor.custom_args.tracking_method in TRACKERS, f"'{predictor.custom_args.tracking_method}' is not supported. Supported ones are {TRACKERS}"

    tracking_config = TRACKER_CONFIGS / (predictor.custom_args.tracking_method + '.yaml')
    trackers = []
    for i in range(predictor.dataset.bs):
        tracker = create_tracker(
            predictor.custom_args.tracking_method,
            tracking_config,
            predictor.custom_args.reid_model,
            predictor.device,
            predictor.custom_args.half,
            predictor.custom_args.per_class
        )
        if hasattr(tracker, 'model'):
            tracker.model.warmup()
        trackers.append(tracker)

    predictor.trackers = trackers

@torch.no_grad()
def run(args):
    if args.imgsz is None:
        args.imgsz = default_imgsz(args.yolo_model)
    yolo = YOLO(args.yolo_model if is_ultralytics_model(args.yolo_model) else 'yolov8n.pt')

    results = yolo.track(
        source=args.source,
        conf=args.conf,
        iou=args.iou,
        agnostic_nms=args.agnostic_nms,
        show=False,
        stream=True,
        device=args.device,
        show_conf=args.show_conf,
        save_txt=args.save_txt,
        show_labels=args.show_labels,
        save=args.save,
        verbose=args.verbose,
        exist_ok=args.exist_ok,
        project=args.project,
        name=args.name,
        classes=args.classes,
        imgsz=args.imgsz,
        vid_stride=args.vid_stride,
        line_width=args.line_width
    )

    yolo.add_callback('on_predict_start', partial(on_predict_start, persist=True))

    if not is_ultralytics_model(args.yolo_model):
        m = get_yolo_inferer(args.yolo_model)
        yolo_model = m(model=args.yolo_model, device=yolo.predictor.device, args=yolo.predictor.args)
        yolo.predictor.model = yolo_model

        if not is_ultralytics_model(args.yolo_model):
            yolo.add_callback("on_predict_batch_start", lambda p: yolo_model.update_im_paths(p))
            yolo.predictor.preprocess = lambda imgs: yolo_model.preprocess(im=imgs)
            yolo.predictor.postprocess = lambda preds, im, im0s: yolo_model.postprocess(preds=preds, im=im, im0s=im0s)

    yolo.predictor.custom_args = args

    for r in results:
        chair_boxes = [d.xyxy[0].tolist() for d in r.boxes if r.names[int(d.cls[0])] == 'chair']
        for d in r.boxes:
            cls = r.names[int(d.cls[0])]
            if cls != 'person':
                continue
            person_id = int(d.id[0]) if d.id is not None else None
            if person_id is None:
                continue
            person_box = d.xyxy[0].tolist()

            matched = False
            for chair_box in chair_boxes:
                if iou(person_box, chair_box) > 0.5:
                    matched = True
                    break

            if matched:
                if person_id not in sitting_log or 'end' in sitting_log[person_id]:
                    sitting_log[person_id] = {'start': datetime.now()}
            else:
                if person_id in sitting_log and 'start' in sitting_log[person_id] and 'end' not in sitting_log[person_id]:
                    sitting_log[person_id]['end'] = datetime.now()
                    start = sitting_log[person_id]['start']
                    end = sitting_log[person_id]['end']
                    duration = (end - start).total_seconds()
                    csv_output.append([person_id, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"), duration])

        img = yolo.predictor.trackers[0].plot_results(r.orig_img, args.show_trajectories)
        if args.show is True:
            cv2.imshow('BoxMOT', img)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(' ') or key == ord('q'):
                break

    df = pd.DataFrame(csv_output, columns=["Person ID", "Start Time", "End Time", "Duration (sec)"])
    df.to_csv("sitting_log.csv", index=False)
    print("📝 Sitting log saved to sitting_log.csv")

def parse_opt():
    parser = argparse.ArgumentParser()
    parser.add_argument('--yolo-model', type=Path, default=WEIGHTS / 'yolov8n', help='yolo model path')
    parser.add_argument('--reid-model', type=Path, default=WEIGHTS / 'osnet_x0_25_msmt17.pt', help='reid model path')
    parser.add_argument('--tracking-method', type=str, default='deepocsort', help='deepocsort, botsort, strongsort, ocsort, bytetrack, imprassoc, boosttrack')
    parser.add_argument('--source', type=str, default='0', help='file/dir/URL/glob, 0 for webcam')
    parser.add_argument('--imgsz', '--img', '--img-size', nargs='+', type=int, default=None, help='inference size h,w')
    parser.add_argument('--conf', type=float, default=0.5, help='confidence threshold')
    parser.add_argument('--iou', type=float, default=0.7, help='intersection over union (IoU) threshold for NMS')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--show', action='store_true', help='display tracking video results')
    parser.add_argument('--save', action='store_true', help='save video tracking results')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --classes 0, or --classes 0 2 3')
    parser.add_argument('--project', default=ROOT / 'runs' / 'track', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--half', action='store_true', help='use FP16 half-precision inference')
    parser.add_argument('--vid-stride', type=int, default=1, help='video frame-rate stride')
    parser.add_argument('--show-labels', action='store_false', help='either show all or only bboxes')
    parser.add_argument('--show-conf', action='store_false', help='hide confidences when show')
    parser.add_argument('--show-trajectories', action='store_true', help='show confidences')
    parser.add_argument('--save-txt', action='store_true', help='save tracking results in a txt file')
    parser.add_argument('--save-id-crops', action='store_true', help='save each crop to its respective id folder')
    parser.add_argument('--line-width', default=None, type=int, help='The line width of the bounding boxes. If None, it is scaled to the image size.')
    parser.add_argument('--per-class', default=False, action='store_true', help='not mix up classes when tracking')
    parser.add_argument('--verbose', default=True, action='store_true', help='print results per frame')
    parser.add_argument('--agnostic-nms', default=False, action='store_true', help='class-agnostic NMS')
    opt = parser.parse_args()
    return opt

if __name__ == "__main__":
    opt = parse_opt()
    run(opt)
