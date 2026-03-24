import base from './base.js';
import joint from './joint.js';
import pose from './pose.js';
import ee from './end-effector.js';
import tts from './tts.js';
import camera from './camera.js';
import apriltag from './apriltag.js';
import db from './database.js';
import sync from './sync.js';

export const modules = [base, joint, pose, ee, tts, camera, apriltag, db, sync];
export const moduleByKey = key => modules.find(module => module.key === key);
