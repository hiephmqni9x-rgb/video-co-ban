import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame} from 'remotion';

export type Subtitle = {startFrame: number; endFrame: number; text: string};
export type Timeline = {
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
  subtitles: Subtitle[];
};

export const BasicVideo: React.FC<{timeline: Timeline}> = ({timeline}) => {
  const frame = useCurrentFrame();
  const subtitle = timeline.subtitles.find((item) => frame >= item.startFrame && frame < item.endFrame);
  const fontSize = Math.round(Math.min(timeline.width * 0.052, timeline.height * 0.042));

  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <OffthreadVideo src={staticFile('clean.mp4')} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      {subtitle && (
        <div style={{
          position: 'absolute', left: '8%', right: '8%', bottom: '12%',
          color: 'white', fontFamily: 'Arial, sans-serif', fontWeight: 700,
          fontSize, lineHeight: 1.2, textAlign: 'center', whiteSpace: 'pre-line',
          textShadow: '0 2px 5px black, 0 0 2px black',
        }}>{subtitle.text}</div>
      )}
    </AbsoluteFill>
  );
};


