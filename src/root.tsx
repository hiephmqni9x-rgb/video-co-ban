import React from 'react';
import {Composition, staticFile} from 'remotion';
import {BasicVideo, type Timeline} from './video';

const fallback: Timeline = {width: 1080, height: 1920, fps: 30, durationInFrames: 30, subtitles: []};

export const Root: React.FC = () => (
  <Composition
    id="BasicVideo"
    component={BasicVideo}
    width={fallback.width}
    height={fallback.height}
    fps={fallback.fps}
    durationInFrames={fallback.durationInFrames}
    defaultProps={{timeline: fallback}}
    calculateMetadata={async () => {
      const response = await fetch(staticFile('timeline.json'));
      if (!response.ok) throw new Error('Run python editor.py prepare first');
      const timeline = (await response.json()) as Timeline;
      return {
        width: timeline.width,
        height: timeline.height,
        fps: timeline.fps,
        durationInFrames: timeline.durationInFrames,
        props: {timeline},
      };
    }}
  />
);


