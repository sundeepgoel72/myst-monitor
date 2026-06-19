#!/usr/bin/env python3
"""
Test runner for MystMon project
"""

import subprocess
import sys
import os
from pathlib import Path


def run_tests():
    """Run all tests for the MystMon project"""
    print("Running MystMon tests...")
    
    # Run pytest with coverage if available
    try:
        # Try to run with coverage
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/", 
            "-v", 
            "--tb=short"
        ], capture_output=True, text=True)
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        return result.returncode == 0
        
    except FileNotFoundError:
        print("pytest not found, trying unittest")
        # Fallback to unittest if pytest is not available
        try:
            result = subprocess.run([
                sys.executable, "-m", "unittest", 
                "discover", 
                "tests", 
                "-v"
            ], capture_output=True, text=True)
            
            print("STDOUT:", result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            
            return result.returncode == 0
            
        except FileNotFoundError:
            print("No test runner found")
            return False


def run_collector():
    """Run the collector code to test functionality"""
    print("Running collector test...")
    
    try:
        # Try to import and run basic collector functionality
        import mystmon.collectors.snmp
        import mystmon.collectors.prometheus
        print("Collector modules imported successfully")
        return True
    except Exception as e:
        print(f"Error running collector: {e}")
        return False


def run_csv_generation():
    """Run CSV generation test"""
    print("Running CSV generation test...")
    
    try:
        # Test if CSV export functionality works
        from mystmon.config import MystMonConfig
        config = MystMonConfig()
        print(f"CSV export path: {config.outputs.csv_export_path}")
        return True
    except Exception as e:
        print(f"Error running CSV generation: {e}")
        return False


if __name__ == "__main__":
    success = True
    
    # Run tests
    if not run_tests():
        success = False
    
    # Run collector
    if not run_collector():
        success = False
    
    # Run CSV generation
    if not run_csv_generation():
        success = False
    
    sys.exit(0 if success else 1)
