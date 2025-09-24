import argparse
import os
import logging
from fitparse import FitFile
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.animation import PillowWriter
from matplotlib.animation import FFMpegWriter
from geopy.distance import geodesic
from pyproj import Transformer
import geopandas as gpd
from shapely.geometry import LineString
import contextily as ctx
from scipy.signal import savgol_filter
from pathlib import Path

class RideRouteAnimator:
    def __init__(self, input_path: Path, output_path: Path, *, logger=None, **kwargs):
        
        # Store CLI arguments and initialize data containers
        self.logger = logger or logging.getLogger(__name__)

        self.input_path = input_path    # Input FIT file
        self.output_path = output_path  # Output video file
        self.dpi = kwargs.get("dpi", 100)   # Output video DPI
        self.zoom = kwargs.get("zoom", 13)  # Tile zoom level
        self.fps = kwargs.get("fps", 10)    # Animation frame rate
        self.tile = kwargs.get("tile", "OpenStreetMap.Mapnik")  # Tile provider
        self.no_elevation_smoothing = kwargs.get("no_elevation_smoothing", False)   # Disable elevation smoothing
        self.overlay_style = kwargs.get("overlay_style", "bottom-right")  # Overlay text position
        self.title = kwargs.get("title", "")    # Title text
        self.start_frame = kwargs.get("start_frame", 0) # Start frame index
        self.end_frame = kwargs.get("end_frame", 0) # End frame index
        self.step_frame = kwargs.get("step_frame", 10)  # Frame step interval
        
        self.track = []             # Parsed FIT records
        self.points = []            # (lat, lon) tuples
        self.times = []             # Timestamps
        self.alts = []              # Altitudes
        self.speeds = []            # Speeds in m/s
        self.hr = []                # Heart rate values
        self.cad = []               # Cadence values
        self.distances = []         # Cumulative distances in meters
        self.merc_x = []            # X coordinates in Web Mercator
        self.merc_y = []            # Y coordinates in Web Mercator
        self.elevations = []        # Smoothed elevation values
        self.sampled_distances = [] # Distances used for elevation plot

    def load_fit(self):
        """Load FIT file and extract relevant data fields"""
        try:
            fitfile = FitFile(str(self.input_path))
        except Exception as e:
            self.logger.error(f"Failed to read FIT file: {e}")
            raise RuntimeError(f"Failed to read FIT file: {e}")

        for record in fitfile.get_messages('record'):
            try:
                lat_raw = record.get_value('position_lat')
                lon_raw = record.get_value('position_long')
                alt     = record.get_value('enhanced_altitude') or record.get_value('altitude')
                time    = record.get_value('timestamp')
                speed   = record.get_value('speed')       # m/s
                hr      = record.get_value('heart_rate')  # bpm
                cad     = record.get_value('cadence')     # rpm

                if None not in (lat_raw, lon_raw, alt, time):
                    '''
                    In Garmin's FIT format, GPS coordinates are recorded in units called "semicircles."
                    These are integer values ​​that represent the entire Earth on the following scale:
                    2^31 semicircles = 180 degrees (a hemisphere)
                    '''
                    lat = lat_raw * (180 / 2**31)
                    lon = lon_raw * (180 / 2**31)
                    self.track.append({'lat': lat, 'lon': lon, 'alt': alt, 'time': time})
                    self.speeds.append(speed)
                    self.hr.append(hr)
                    self.cad.append(cad)
            except Exception as e:
                self.logger.warning(f"Skipping malformed record: {e}")

        if not self.track:
            self.logger.error("No valid track points found in FIT file.")
            raise RuntimeError("No valid track points found in FIT file.")
    
    def compute_moving_time(self):
        """Calculate moving time using time delta and speed threshold"""
        moving_time = 0
        speed_threshold = 2.0  # m/s ≈ 7.2 km/h

        for i in range(1, len(self.track)):
            speed = self.speeds[i]
            if speed and speed > speed_threshold:
                t1 = self.track[i-1]['time']
                t2 = self.track[i]['time']
                delta = (t2 - t1).total_seconds()
                moving_time += delta
        return moving_time

    def compute_elevation_gain(self):
        """Calculate elevation gain with minimum segment length and gradient filtering"""
        # Basic elevation gain calculation (commented out)
        # self.elevation_gain = sum(
        #     max(self.elevations[i] - self.elevations[i-1], 0)
        #     for i in range(1, len(self.elevations))
        #     if abs(self.elevations[i] - self.elevations[i-1]) > 3
        # )
        gain = 0
        accum_elev = 0
        accum_dist = 0
        min_segment = 100 # meters
        min_gradient = 0.005    # 0.5%

        for i in range(1, len(self.elevations)):
            delta_elev = self.elevations[i] - self.elevations[i-1]
            delta_dist = self.distances[i] - self.distances[i-1]

            accum_dist += delta_dist
            accum_elev += delta_elev
                
            if accum_dist >= min_segment:
                gradient = accum_elev / accum_dist
                if gradient >= min_gradient:
                    gain += accum_elev
                accum_elev = 0
                accum_dist = 0
        return gain 

    def compute_geometry(self):
        """Compute distances, coordinate transformation, elevation smoothing, and summary statistics"""
        self.points = [(d['lat'], d['lon']) for d in self.track]
        self.times  = [d['time'] for d in self.track]
        self.alts   = [d['alt']  for d in self.track]

        # Calculate cumulative distance between each point
        self.distances = [0.0]
        for i in range(1, len(self.points)):
            d = geodesic(self.points[i-1], self.points[i]).meters
            self.distances.append(self.distances[-1] + d)

        # Convert coordinates to Web Mercator (EPSG:3857)
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        self.merc_x, self.merc_y = zip(*[
            transformer.transform(lon, lat) for lat, lon in self.points
        ])

         # Apply elevation smoothing unless disabled
        if self.no_elevation_smoothing:
            self.elevations = self.alts
        else:
            try:
                self.elevations = savgol_filter(self.alts, window_length=11, polyorder=2)
            except Exception as e:
                self.logger.warning(f"Elevation smoothing failed: {e}")
                self.elevations = self.alts

        # Compute summary statistics
        self.total_time = (self.times[-1] - self.times[0]).total_seconds()
        self.moving_time = self.compute_moving_time()
        
        self.logger.debug(f"Total time: {self.total_time/60:.1f} min")
        self.logger.debug(f"Moving time: {self.moving_time/60:.1f} min")
        
        self.elevation_gain = self.compute_elevation_gain()
        self.avg_speed_kmh = (self.distances[-1] / self.moving_time) * 3.6
        self.avg_hr = self._average_nonzero(self.hr)
        self.avg_cad = self._average_nonzero(self.cad)

    def _average_nonzero(self, values):
        """Calculate average of non-zero values"""
        valid = [v for v in values if v]
        return sum(valid) / len(valid) if valid else 0
    
    def render_animation(self):
        """Render map, elevation graph, animation frames, and save as video"""
        # Create LineString geometry from GPS points
        line = LineString([(lon, lat) for lat, lon in self.points])
        gdf = gpd.GeoDataFrame(geometry=[line], crs="EPSG:4326").to_crs(epsg=3857)
        bounds = gdf.total_bounds

        # Create figure and subplots for map and elevation
        figsize= (12, 9)
        height_ratios = (10, 2)
        fig, (ax_map, ax_elev) = plt.subplots(2, 1, figsize=figsize,
            gridspec_kw={'height_ratios': height_ratios})
        fig.set_dpi(self.dpi)
        plt.subplots_adjust(hspace=0)
        fig.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05)

        # Plot route line on map
        gdf.plot(ax=ax_map, linewidth=2, color='blue')

        # Add margin around route bounds
        x_margin = (bounds[2] - bounds[0]) * 0.01
        y_margin = (bounds[3] - bounds[1]) * 0.01
        ax_map.set_xlim(bounds[0] - x_margin, bounds[2] + x_margin)
        ax_map.set_ylim(bounds[1] - y_margin, bounds[3] + y_margin)
                
        # Hide axis ticks and labels
        ax_map.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

        # Load background tile map
        try:
            provider = self.tile.split(".")
            tile_source = getattr(ctx.providers[provider[0]], provider[1])
            ctx.add_basemap(ax_map, source=tile_source,
                            zoom=self.zoom, reset_extent=False)
        except Exception as e:
            self.logger.error(f"Failed to load tile provider '{self.tile}': {e}")
            raise RuntimeError(f"Failed to load tile provider '{self.tile}': {e}")

        # Initialize route marker
        marker, = ax_map.plot([], [], 'ro')

        # Plot elevation profile
        self.sampled_distances = [d / 1000 for d in self.distances]
        ax_elev.plot(self.sampled_distances, self.elevations, color='gray')
        ax_elev.fill_between(self.sampled_distances, self.elevations, color='gray', alpha=0.3)
        ax_elev.set_ylabel("Elevation (m)", fontsize=10)
        ax_elev.set_xlabel("Distance (km)")
        ax_elev.tick_params(axis='both', labelsize=8)
        ax_elev.grid(True, linestyle='--', alpha=0.5)
        ax_elev.set_xlim(min(self.sampled_distances), max(self.sampled_distances))
        
        # Plot speed profile
        ax_speed = ax_elev.twinx()
        speeds_kmh = [s * 3.6 if s else 0 for s in self.speeds]
        ax_speed.plot(self.sampled_distances, speeds_kmh, color='blue', alpha=0.5)
        ax_speed.set_ylabel("Speed (km/h)", fontsize=10)
        ax_speed.tick_params(axis='y', labelsize=8, labelcolor='blue')
        
        elev_cursor = ax_elev.axvline(x=0, color='red')
        ax_map.set_title(self.title, fontsize=14, pad=5)
        
        # Determine overlay text position
        positions = {
            "top-left":     (0.01, 0.90),
            "top-right":    (0.75, 0.90),
            "bottom-left":  (0.01, 0.05),
            "bottom-right": (0.75, 0.05),
        }
        x, y = positions[self.overlay_style]
        info_text = ax_map.text(x, y, "", transform=ax_map.transAxes,
                                fontsize=10, color="white",
                                bbox=dict(facecolor="black", alpha=0.5))

        def update(frame):
            # Update route marker and elevation cursor
            marker.set_data([self.merc_x[frame]], [self.merc_y[frame]])
            d = self.sampled_distances[frame]
            elev_cursor.set_xdata([d, d])

            # Extract current metrics
            speed_kmh = self.speeds[frame] * 3.6 if self.speeds[frame] else 0
            elevation = self.elevations[frame]
            hr        = self.hr[frame] if self.hr[frame] else "-"
            cad       = self.cad[frame] if self.cad[frame] else "-"

            # Update overlay text
            info_text.set_text(
                f"Speed: {speed_kmh:.1f} km/h\n"
                f"Elevation: {elevation:.1f} m\n"
                f"HR: {hr} bpm\n"
                f"Cadence: {cad} rpm\n"
                f"Distance: {d:.2f} km\n"
                f"Elevation Gain: {self.elevation_gain:.1f} m\n"
                f"Avg Speed: {self.avg_speed_kmh:.1f} km/h\n"
                f"Avg HR: {self.avg_hr:.0f} bpm\n"
                f"Avg Cadence: {self.avg_cad:.0f} rpm"
            )
            return marker, elev_cursor, info_text
        
        # Determine frame range and step
        start = max(0, self.start_frame)
        end = self.end_frame if self.end_frame > 0 else len(self.points)
        end = min(end, len(self.points))
        step = max(1, self.step_frame)

        if start >= end:
            self.logger.error(f"Invalid frame range: start={start}, end={end}")
            raise RuntimeError(f"Invalid frame range: start={start}, end={end}")

        frames = range(start, end, step)

        # Create and save animation
        try:
            ani = animation.FuncAnimation(
                fig, update,
                frames=frames,
                interval=int(1000 / self.fps),
                blit=True
            )          
            
            if self.output_path.suffix.lower() == ".gif":
                writer = PillowWriter(fps=self.fps)
            else:
                writer = FFMpegWriter(fps=self.fps, codec="h264", bitrate=3000)
            ani.save(self.output_path, writer=writer, dpi=self.dpi)
            self.logger.info(f"Animation saved to: {self.output_path}")
        except Exception as e:
            self.logger.error(f"Failed to save animation: {e}")
            raise RuntimeError(f"Failed to save animation: {e}")

    def run(self):
        """Execute the full animation workflow"""
        self.logger.info(f"Loading FIT file {self.input_path}...")
        self.load_fit()
        self.logger.info("Computing geometry and statistics...")
        self.compute_geometry()
        self.logger.info("Rendering and saving animation...")
        self.render_animation()
        
        return str(self.output_path)

def list_tile_providers():
    """Recursively list available tile providers from contextily.providers"""
    import contextily as ctx

    def walk_providers(obj, path=""):
        results = []
        for name in dir(obj):
            if name.startswith("_"):
                continue
            try:
                attr = getattr(obj, name)
            except Exception:
                continue
            full_path = f"{path}.{name}" if path else name
            if hasattr(attr, "url"):
                results.append(full_path)
            elif hasattr(attr, "__dict__"):
                results.extend(walk_providers(attr, full_path))
        return results

    tiles = walk_providers(ctx.providers)
    print("Available tile providers:")
    for t in sorted(tiles):
        print(f"  {t}")

def main():
    
    # Set logging level based on environment variable LOG_LEVEL (default: INFO)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    
    parser = argparse.ArgumentParser(description="Generate route animation from FIT file")
    parser.add_argument("-i", "--input", default="input.fit", help="Input FIT file")
    parser.add_argument("-o", "--output", default="output.mp4", help="Output MP4 file")
    parser.add_argument("--dpi", type=int, default=100, help="Output video DPI")
    parser.add_argument("--zoom", type=int, default=13, help="Tile zoom level")
    parser.add_argument("--fps", type=int, default=10, help="Animation frame rate")
    parser.add_argument("--tile", default="OpenStreetMap.Mapnik",
                        help="Tile provider name for background map (e.g. OpenStreetMap.Mapnik)")
    parser.add_argument("--no-elevation-smoothing", action="store_true",
                        help="Disable elevation smoothing")
    parser.add_argument("--overlay-style", default="bottom-right",
                        choices=["top-left", "top-right", "bottom-left", "bottom-right"],
                        help="Overlay text position")
    parser.add_argument("--tilelist", action="store_true", help="List available tile providers and exit")
    parser.add_argument("--title", default="your ride route", help="Title to embed in the video")
    parser.add_argument("--start-frame", type=int, default=0,help="Start frame index (default: 0)")
    parser.add_argument("--end-frame", type=int, default=0, help="End frame index (default: 0 means full length)")
    parser.add_argument("--step-frame", type=int, default=1,help="Frame step interval (default: 10 means every frame)")

    args = parser.parse_args()
    
    if args.tilelist:
        list_tile_providers()
        return

    try:
        RideRouteAnimator(Path(args.input), Path(args.output), logger=logger, **vars(args)).run()
    except Exception as e:
        logger.exception("Unexpected error occurred.")
        raise RuntimeError("An error occurred during processing. See logs for details.")

if __name__ == "__main__":
    main()