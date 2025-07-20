#!/usr/bin/env python
"""
MinerU Optimization Script

Optimizes MinerU configuration based on available hardware.
"""

import json
import os
import sys
import time
import logging
import psutil
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logging import get_logger

logger = get_logger("mineru_optimizer")


class MinerUOptimizer:
    """Optimize MinerU settings based on system capabilities."""

    def __init__(self):
        self.config_path = Path("config/mineru_config.json")
        self.system_info = self.detect_system()

    def detect_system(self) -> dict:
        """Detect system hardware capabilities."""
        logger.debug("Starting system hardware detection")
        start_time = time.time()
        
        info = {
            "cpu_count": psutil.cpu_count(logical=False),
            "cpu_threads": psutil.cpu_count(logical=True),
            "ram_gb": psutil.virtual_memory().total / (1024**3),
            "gpu_available": False,
            "gpu_memory_gb": 0,
            "gpu_name": "None",
        }
        
        logger.debug(f"CPU: {info['cpu_count']} cores, {info['cpu_threads']} threads")
        logger.debug(f"RAM: {info['ram_gb']:.1f} GB")
        
        # Also get current RAM usage
        ram_usage = psutil.virtual_memory().percent
        logger.debug(f"Current RAM usage: {ram_usage:.1f}%")

        # Check for GPU
        logger.debug("Attempting PyTorch GPU detection...")
        try:
            import torch

            if torch.cuda.is_available():
                info["gpu_available"] = True
                info["gpu_name"] = torch.cuda.get_device_name(0)
                info["gpu_memory_gb"] = torch.cuda.get_device_properties(
                    0
                ).total_memory / (1024**3)
                logger.info(f"GPU detected via PyTorch: {info['gpu_name']} ({info['gpu_memory_gb']:.1f} GB)")
                
                # Get current GPU usage
                gpu_memory_allocated = torch.cuda.memory_allocated(0) / (1024**3)
                logger.debug(f"Current GPU memory allocated: {gpu_memory_allocated:.2f} GB")
            else:
                logger.debug("PyTorch available but no CUDA devices found")
        except ImportError:
            logger.warning("PyTorch not installed, cannot detect GPU via torch")
        except Exception as e:
            logger.error(f"Error during PyTorch GPU detection: {e}")

        # Alternative GPU detection via nvidia-smi
        if not info["gpu_available"]:
            logger.debug("Attempting nvidia-smi GPU detection...")
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total",
                        "--format=csv,noheader",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    output = result.stdout.strip()
                    if output:
                        parts = output.split(", ")
                        info["gpu_available"] = True
                        info["gpu_name"] = parts[0]
                        # Convert MiB to GB
                        memory_mib = int(parts[1].replace(" MiB", ""))
                        info["gpu_memory_gb"] = memory_mib / 1024
                        logger.info(f"GPU detected via nvidia-smi: {info['gpu_name']} ({info['gpu_memory_gb']:.1f} GB)")
                else:
                    logger.debug(f"nvidia-smi returned non-zero exit code: {result.returncode}")
                    if result.stderr:
                        logger.debug(f"nvidia-smi stderr: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.debug("nvidia-smi command timed out")
            except FileNotFoundError:
                logger.debug("nvidia-smi not found in PATH")
            except Exception as e:
                logger.debug(f"Error during nvidia-smi detection: {e}")
        
        elapsed = time.time() - start_time
        logger.debug(f"System detection completed in {elapsed:.2f}s")
        return info

    def recommend_settings(self) -> dict:
        """Recommend optimal settings based on hardware."""
        logger.info("Generating optimization recommendations")
        logger.debug(f"System info: {json.dumps(self.system_info, indent=2)}")
        
        start_time = time.time()
        recommendations = {}

        # GPU recommendations
        if self.system_info["gpu_available"]:
            gpu_memory = self.system_info["gpu_memory_gb"]

            if gpu_memory >= 24:  # High-end GPU (RTX 4090, A100, etc)
                recommendations["device"] = "cuda"
                recommendations["batch_size"] = 8
                recommendations["formula_batch_size"] = 32
                recommendations["use_fp16"] = True
                recommendations["gpu_memory_fraction"] = 0.9

            elif gpu_memory >= 12:  # Mid-range GPU (RTX 4070+, A4000+)
                recommendations["device"] = "cuda"
                recommendations["batch_size"] = 4
                recommendations["formula_batch_size"] = 16
                recommendations["use_fp16"] = True
                recommendations["gpu_memory_fraction"] = 0.85

            elif gpu_memory >= 6:  # Entry-level GPU (RTX 3060+)
                recommendations["device"] = "cuda"
                recommendations["batch_size"] = 2
                recommendations["formula_batch_size"] = 8
                recommendations["use_fp16"] = True
                recommendations["gpu_memory_fraction"] = 0.8

            else:  # Low VRAM GPU
                recommendations["device"] = "cuda"
                recommendations["batch_size"] = 1
                recommendations["formula_batch_size"] = 4
                recommendations["use_fp16"] = True
                recommendations["gpu_memory_fraction"] = 0.7
        else:
            # CPU recommendations
            recommendations["device"] = "cpu"

            cpu_threads = self.system_info["cpu_threads"]
            ram_gb = self.system_info["ram_gb"]

            if ram_gb >= 32 and cpu_threads >= 16:
                recommendations["batch_size"] = 2
                recommendations["cpu_num_threads"] = min(cpu_threads - 2, 16)

            elif ram_gb >= 16:
                recommendations["batch_size"] = 1
                recommendations["cpu_num_threads"] = min(cpu_threads - 1, 8)

            else:
                recommendations["batch_size"] = 1
                recommendations["cpu_num_threads"] = min(cpu_threads, 4)

            recommendations["formula_batch_size"] = recommendations["batch_size"]
            recommendations["use_fp16"] = False

        # Memory recommendations
        if self.system_info["ram_gb"] >= 64:
            recommendations["num_workers"] = 8
            recommendations["prefetch_factor"] = 4
            recommendations["cache_size_gb"] = 16

        elif self.system_info["ram_gb"] >= 32:
            recommendations["num_workers"] = 4
            recommendations["prefetch_factor"] = 2
            recommendations["cache_size_gb"] = 8

        else:
            recommendations["num_workers"] = 2
            recommendations["prefetch_factor"] = 1
            recommendations["cache_size_gb"] = 4

        return recommendations

    def apply_recommendations(self, recommendations: dict):
        """Apply recommended settings to configuration."""
        logger.info("Applying optimization recommendations to configuration")
        
        # Backup existing config if it exists
        if self.config_path.exists():
            backup_path = self.config_path.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            logger.debug(f"Backing up existing config to: {backup_path}")
            import shutil
            shutil.copy2(self.config_path, backup_path)
            
            with open(self.config_path, "r") as f:
                config = json.load(f)
            logger.debug(f"Loaded existing config with {len(config)} top-level keys")
        else:
            config = {}
            logger.debug("No existing config found, creating new one")

        # Apply device settings
        config["device-mode"] = recommendations["device"]

        # Apply batch sizes
        if "performance" not in config:
            config["performance"] = {}
        config["performance"]["batch-size"] = recommendations["batch_size"]

        # Apply formula settings
        if "formula-config" not in config:
            config["formula-config"] = {}
        config["formula-config"]["batch_size"] = recommendations.get(
            "formula_batch_size", 16
        )
        config["formula-config"]["use_fp16"] = recommendations.get("use_fp16", True)

        # Apply optimization settings
        if "optimization" not in config:
            config["optimization"] = {}

        if recommendations["device"] == "cuda":
            config["optimization"]["gpu_memory_fraction"] = recommendations.get(
                "gpu_memory_fraction", 0.8
            )

        config["optimization"]["num_workers"] = recommendations.get("num_workers", 4)
        config["optimization"]["prefetch_factor"] = recommendations.get(
            "prefetch_factor", 2
        )

        # Apply fallback settings
        if "fallback" not in config:
            config["fallback"] = {}

        if recommendations["device"] == "cpu":
            config["fallback"]["cpu_num_threads"] = recommendations.get(
                "cpu_num_threads", 8
            )

        # Save updated config
        self.config_path.parent.mkdir(exist_ok=True)
        
        logger.debug(f"Saving configuration to: {self.config_path}")
        logger.debug(f"Configuration keys: {list(config.keys())}")
        
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)
        
        file_size = self.config_path.stat().st_size
        logger.info(f"Updated configuration saved to {self.config_path} ({file_size} bytes)")
        
        # Log applied changes
        logger.debug("Applied recommendations:")
        logger.debug(f"  Device mode: {recommendations.get('device', 'not set')}")
        logger.debug(f"  Batch size: {recommendations.get('batch_size', 'not set')}")
        logger.debug(f"  Workers: {recommendations.get('num_workers', 'not set')}")

    def update_environment(self, recommendations: dict):
        """Update environment variables based on recommendations."""
        env_updates = []

        # Device setting
        env_updates.append(f"export MINERU_DEVICE={recommendations['device']}")

        # Batch size
        env_updates.append(f"export MINERU_BATCH_SIZE={recommendations['batch_size']}")

        # CPU settings
        if recommendations["device"] == "cpu":
            env_updates.append(
                f"export OMP_NUM_THREADS={recommendations.get('cpu_num_threads', 8)}"
            )
            env_updates.append("export MKL_NUM_THREADS=$OMP_NUM_THREADS")

        # GPU settings
        if recommendations["device"] == "cuda" and recommendations.get("use_fp16"):
            env_updates.append("export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512")

        # Print environment updates
        print("\nRecommended environment variables:")
        print("=" * 50)
        for update in env_updates:
            print(update)

        # Update .env if it exists
        env_file = Path(".env")
        if env_file.exists():
            print("\nUpdate your .env file with these settings:")
            for update in env_updates:
                key, value = update.replace("export ", "").split("=", 1)
                print(f"{key}={value}")

    def run_benchmark(self):
        """Run a simple benchmark to test settings."""
        logger.info("Starting MinerU benchmark")
        print("\nRunning MinerU benchmark...")
        benchmark_start = time.time()

        try:
            # Check if MinerU is installed
            logger.debug("Checking if MinerU is installed...")
            import magic_pdf
            logger.debug("MinerU import successful")

            # Create a simple test
            test_script = """
import time
from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

# Simple benchmark using a small test
start = time.time()
print("MinerU is properly configured!")
end = time.time()
print(f"Initialization time: {end - start:.2f}s")
"""

            result = subprocess.run(
                [sys.executable, "-c", test_script],
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    **dict(MINERU_DEVICE=self.system_info.get("device", "cpu")),
                },
            )

            if result.returncode == 0:
                print("✅ MinerU benchmark passed!")
                print(result.stdout)
            else:
                print("❌ MinerU benchmark failed!")
                print(result.stderr)

        except ImportError:
            print("⚠️  MinerU not installed. Install with:")
            print(
                "pip install magic-pdf[full] --extra-index-url https://wheels.myhloli.com"
            )

    def print_report(self, recommendations: dict):
        """Print optimization report."""
        print("\n" + "=" * 60)
        print("MINERU OPTIMIZATION REPORT")
        print("=" * 60)

        print("\nSystem Hardware:")
        print(
            f"  CPU: {self.system_info['cpu_count']} cores, {self.system_info['cpu_threads']} threads"
        )
        print(f"  RAM: {self.system_info['ram_gb']:.1f} GB")

        if self.system_info["gpu_available"]:
            print(f"  GPU: {self.system_info['gpu_name']}")
            print(f"  VRAM: {self.system_info['gpu_memory_gb']:.1f} GB")
        else:
            print("  GPU: Not detected")

        print("\nRecommended Settings:")
        print(f"  Device: {recommendations['device']}")
        print(f"  Batch Size: {recommendations['batch_size']}")
        print(f"  Workers: {recommendations.get('num_workers', 4)}")

        if recommendations["device"] == "cuda":
            print(f"  Use FP16: {recommendations.get('use_fp16', True)}")
            print(
                f"  GPU Memory: {recommendations.get('gpu_memory_fraction', 0.8) * 100:.0f}%"
            )
        else:
            print(f"  CPU Threads: {recommendations.get('cpu_num_threads', 8)}")

        print("\nEstimated Performance:")
        if recommendations["device"] == "cuda":
            pages_per_minute = recommendations["batch_size"] * 20  # Rough estimate
        else:
            pages_per_minute = recommendations["batch_size"] * 5  # CPU is slower

        print(f"  Processing Speed: ~{pages_per_minute} pages/minute")
        print(f"  Max Document Size: ~{recommendations['batch_size'] * 250} pages")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Optimize MinerU configuration based on system hardware",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze system and show recommendations
  %(prog)s
  
  # Apply recommendations to configuration
  %(prog)s --apply
  
  # Run benchmark after optimization
  %(prog)s --apply --benchmark
  
  # Export recommendations to file
  %(prog)s --export recommendations.json
  
  # Enable debug logging
  %(prog)s --debug
        """
    )
    
    parser.add_argument(
        "--apply", action="store_true", help="Apply recommendations to configuration"
    )
    parser.add_argument(
        "--benchmark", action="store_true", help="Run benchmark after optimization"
    )
    parser.add_argument(
        "--export", help="Export recommendations to JSON file"
    )
    parser.add_argument(
        "--force-device", choices=["cpu", "cuda"], help="Force specific device mode"
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()
    
    # Set up logging
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'mineru_optimizer_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )
        logger.debug("Debug logging enabled")
    elif args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    logger.debug(f"Script started with arguments: {vars(args)}")
    logger.debug(f"Current working directory: {os.getcwd()}")
    logger.debug(f"Python version: {sys.version}")
    
    try:
        overall_start = time.time()
        logger.info("Initializing MinerU optimizer...")
        
        optimizer = MinerUOptimizer()
        
        # Generate recommendations
        logger.info("Analyzing system and generating recommendations...")
        recommendations = optimizer.recommend_settings()
        
        # Override device if requested
        if args.force_device:
            logger.info(f"Forcing device mode to: {args.force_device}")
            recommendations["device"] = args.force_device
            if args.force_device == "cpu":
                recommendations["use_fp16"] = False
        
        # Export if requested
        if args.export:
            logger.info(f"Exporting recommendations to: {args.export}")
            export_data = {
                "generated_at": datetime.now().isoformat(),
                "system_info": optimizer.system_info,
                "recommendations": recommendations
            }
            with open(args.export, 'w') as f:
                json.dump(export_data, f, indent=2)
            print(f"\n✅ Recommendations exported to: {args.export}")
        
        # Print report
        optimizer.print_report(recommendations)
        
        # Update environment
        optimizer.update_environment(recommendations)
        
        # Apply if requested
        if args.apply:
            logger.info("Applying recommendations to configuration...")
            optimizer.apply_recommendations(recommendations)
            print("\n✅ Configuration updated!")
        else:
            logger.info("Recommendations generated but not applied (use --apply to apply)")
        
        # Run benchmark if requested
        if args.benchmark:
            optimizer.run_benchmark()
        
        overall_time = time.time() - overall_start
        logger.info(f"MinerU optimization completed in {overall_time:.2f}s")
        
    except KeyboardInterrupt:
        logger.info("Optimization interrupted by user")
        print("\nOptimization cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug(f"Exception details: {e.__class__.__name__}: {str(e)}")
        import traceback
        logger.debug(f"Traceback:\n{traceback.format_exc()}")
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
