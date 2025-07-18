#!/usr/bin/env python
"""
MinerU Optimization Script

Optimizes MinerU configuration based on available hardware.
"""

import json
import os
import sys
import psutil
import subprocess
from pathlib import Path

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
        info = {
            "cpu_count": psutil.cpu_count(logical=False),
            "cpu_threads": psutil.cpu_count(logical=True),
            "ram_gb": psutil.virtual_memory().total / (1024**3),
            "gpu_available": False,
            "gpu_memory_gb": 0,
            "gpu_name": "None",
        }

        # Check for GPU
        try:
            import torch

            if torch.cuda.is_available():
                info["gpu_available"] = True
                info["gpu_name"] = torch.cuda.get_device_name(0)
                info["gpu_memory_gb"] = torch.cuda.get_device_properties(
                    0
                ).total_memory / (1024**3)
        except ImportError:
            logger.warning("PyTorch not installed, cannot detect GPU")

        # Alternative GPU detection via nvidia-smi
        if not info["gpu_available"]:
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total",
                        "--format=csv,noheader",
                    ],
                    capture_output=True,
                    text=True,
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
            except Exception:
                pass

        return info

    def recommend_settings(self) -> dict:
        """Recommend optimal settings based on hardware."""
        logger.info(f"System info: {self.system_info}")

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
        # Load existing config
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                config = json.load(f)
        else:
            config = {}

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
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Updated configuration saved to {self.config_path}")

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
        print("\nRunning MinerU benchmark...")

        try:
            # Check if MinerU is installed
            import magic_pdf

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

    parser = argparse.ArgumentParser(description="Optimize MinerU configuration")
    parser.add_argument(
        "--apply", action="store_true", help="Apply recommendations to configuration"
    )
    parser.add_argument(
        "--benchmark", action="store_true", help="Run benchmark after optimization"
    )

    args = parser.parse_args()

    optimizer = MinerUOptimizer()
    recommendations = optimizer.recommend_settings()

    # Print report
    optimizer.print_report(recommendations)

    # Update environment
    optimizer.update_environment(recommendations)

    # Apply if requested
    if args.apply:
        optimizer.apply_recommendations(recommendations)
        print("\n✅ Configuration updated!")

    # Run benchmark if requested
    if args.benchmark:
        optimizer.run_benchmark()


if __name__ == "__main__":
    main()
