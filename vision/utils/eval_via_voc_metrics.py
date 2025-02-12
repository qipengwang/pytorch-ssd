# https://github.com/facebookresearch/Detectron/blob/main/detectron/datasets/voc_eval.py

from typing import Dict, List
import numpy as np
import os
import json


def voc_ap(rec, prec, use_07_metric=False):
    """Compute VOC AP given precision and recall. If use_07_metric is true, uses
    the VOC 07 11-point method (default:False).
    """
    if use_07_metric:
        # 11 point metric
        ap = 0.
        for t in np.arange(0., 1.1, 0.1):
            if np.sum(rec >= t) == 0:
                p = 0
            else:
                p = np.max(prec[rec >= t])
            ap += p / 11.
    else:
        # correct AP calculation
        # first append sentinel values at the end
        mrec = np.concatenate(([0.], rec, [1.]))
        mpre = np.concatenate(([0.], prec, [0.]))

        # compute the precision envelope
        for i in range(mpre.size - 1, 0, -1):
            mpre[i - 1] = np.maximum(mpre[i - 1], mpre[i])

        # to calculate area under PR curve, look for points
        # where X axis (recall) changes value
        i = np.where(mrec[1:] != mrec[:-1])[0]

        # and sum (\Delta recall) * prec
        ap = np.sum((mrec[i + 1] - mrec[i]) * mpre[i + 1])
    return ap


def voc_eval(detpath, annopaths, classid, ovthresh=0.5, use_07_metric=False):
    """
    Top level function that does the PASCAL VOC evaluation.
    detpath: Path to detections file: predictions
    annopath: Path to annotations json file: ground_truth
    imagesetfile: Text file containing the list of images, one image per line.
    classid: Category name (duh)
    cachedir: Directory for caching the annotations
    [ovthresh]: Overlap threshold (default = 0.5)
    [use_07_metric]: Whether to use VOC07's 11 point AP computation
        (default False)
    """
    # assumes detections are in detpath.format(classid)
    # assumes annotations are in annopath.format(imagename)
    # assumes imagesetfile is a text file with each line an image name
    # cachedir caches the annotations in a pickle file

    # TODO: first load gt to recs, and get imagenames: LIST[str]
    # with open(imagesetfile) as f:
    #     imagenames = [x.strip() for x in f]
    
    # extract gt objects for this class
    class_recs = {}
    npos = 0
    if isinstance(annopaths, str):
        annopaths = [annopaths]
    for annopath in annopaths:
        with open(annopath) as f:
            recs = json.load(f)  # Dict[str, List[Dict]]
        for imagename in recs:
            R = [obj 
                 for obj in recs[imagename] 
                    if obj['class'] == classid 
                        and (float(obj['bbox'][2]) - float(obj['bbox'][0])) * (float(obj['bbox'][3]) - float(obj['bbox'][1])) > 1e5]
            bbox = np.array([x['bbox'] for x in R])
            # difficult = np.array([x['difficult'] for x in R]).astype(np.bool)
            det = [False] * len(R)
            npos += len(R)
            class_recs[imagename] = {'bbox': bbox,
                                    #  'difficult': difficult,
                                    'det': det}

    # read dets
    # with open(detpath, 'r') as f:
    #     lines = f.readlines()
    # splitlines = [x.strip().split() for x in lines]
    # image_ids = [x[0] for x in splitlines]
    # confidence = np.array([float(x[1]) for x in splitlines])
    # BB = np.array([[float(z) for z in x[2:]] for x in splitlines])
    with open(detpath) as f:
        dets = json.load(f)
    image_ids, confidence, BB = [], [], []
    for k, vs in dets.items():
        if k not in class_recs: continue
        for v in vs:
            if v['class'] == classid:
                image_ids.append(k)
                confidence.append(v['score'])
                BB.append(v['bbox'])
    if not confidence: return 0, 0, 0
    confidence = np.array(confidence)
    BB = np.array(BB)

    # sort by confidence
    sorted_ind = np.argsort(-confidence)
    BB = BB[sorted_ind, :]
    image_ids = [image_ids[x] for x in sorted_ind]

    # go down dets and mark TPs and FPs
    nd = len(image_ids)
    tp = np.zeros(nd)
    fp = np.zeros(nd)
    for d in range(nd):
        if image_ids[d] not in class_recs: continue
        R = class_recs[image_ids[d]]  # all ground truthes
        bb = BB[d, :].astype(float)  # one detection
        ovmax = -np.inf
        BBGT = R['bbox'].astype(float)

        if BBGT.size > 0:
            # compute overlaps and get max overlap
            # intersection
            ixmin = np.maximum(BBGT[:, 0], bb[0])
            iymin = np.maximum(BBGT[:, 1], bb[1])
            ixmax = np.minimum(BBGT[:, 2], bb[2])
            iymax = np.minimum(BBGT[:, 3], bb[3])
            iw = np.maximum(ixmax - ixmin + 1., 0.)
            ih = np.maximum(iymax - iymin + 1., 0.)
            inters = iw * ih

            # union = A + B - A & B
            uni = (bb[2] - bb[0] + 1.) * (bb[3] - bb[1] + 1.) + (BBGT[:, 2] - BBGT[:, 0] + 1.) * (BBGT[:, 3] - BBGT[:, 1] + 1.) - inters

            overlaps = inters / uni
            ovmax = np.max(overlaps)
            jmax = np.argmax(overlaps)

        if ovmax > ovthresh:
            if not R['det'][jmax]:
                tp[d] = 1.
                R['det'][jmax] = 1
            else:
                fp[d] = 1.
        else:
            fp[d] = 1.

    # compute precision recall
    # print('fp:', fp)
    fp = np.cumsum(fp)
    tp = np.cumsum(tp)
    # print("fuck:", fp.shape, tp.shape, tp)
    rec = tp / float(npos)
    # avoid divide by zero in case the first detection matches a difficult
    # ground truth
    prec = tp / np.maximum(tp + fp, np.finfo(np.float64).eps)
    ap = voc_ap(rec, prec, use_07_metric)

    return rec, prec, ap