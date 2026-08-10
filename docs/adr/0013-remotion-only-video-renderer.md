# Remotion as the Only Video Renderer

ShortsFlow renders every new **Arquivo de Video Final** with Remotion. The former FFmpeg video backend and the parallel premium comparison flow were removed because Remotion already owns the primary `render/final.mp4` contract; maintaining two render paths duplicated configuration, routes, artifacts and tests. FFmpeg remains an implementation dependency for audio processing, media probing and final-file integrity checks.
