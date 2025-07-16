#!/usr/bin/env python3
"""Simple validation test without external dependencies."""

import sys
import os
from datetime import datetime
from uuid import uuid4
from typing import Dict, Any
from enum import Enum

# Add current directory to path
sys.path.insert(0, os.getcwd())

try:
    from models.item5_fees import InitialFee
    from models.item6_other_fees import OtherFee
    from models.item7_investment import InitialInvestment
    from models.item20_outlets import OutletSummary
    from models.item21_financials import Financials
    from models.base import ValidationConfig
    print("✅ Successfully imported all models")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Define validation enums for testing
class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

class ValidationCategory(str, Enum):
    SCHEMA = "SCHEMA"
    BUSINESS_RULE = "BUSINESS_RULE"
    CROSS_FIELD = "CROSS_FIELD"
    RANGE = "RANGE"
    FORMAT = "FORMAT"
    REFERENCE = "REFERENCE"

def test_initial_fee_validation():
    """Test InitialFee validation."""
    print("\n🧪 Testing InitialFee validation...")
    
    # Valid data
    valid_data = {
        "fee_name": "Initial Franchise Fee",
        "amount_cents": 5000000,  # $50,000
        "refundable": True,
        "refund_conditions": "Refundable within 30 days",
        "due_at": "Signing",
        "section_id": uuid4()
    }
    
    try:
        fee = InitialFee.model_validate(valid_data)
        print(f"✅ Valid InitialFee created: {fee.fee_name} - ${fee.amount_cents/100:,.2f}")
    except Exception as e:
        print(f"❌ InitialFee validation failed: {e}")
        return False
    
    # Invalid data - negative amount
    invalid_data = valid_data.copy()
    invalid_data["amount_cents"] = -1000
    
    try:
        fee = InitialFee.model_validate(invalid_data)
        print("❌ Should have failed validation for negative amount")
        return False
    except Exception as e:
        print(f"✅ Correctly rejected negative amount: {e}")
    
    return True

def test_other_fee_validation():
    """Test OtherFee validation."""
    print("\n🧪 Testing OtherFee validation...")
    
    # Valid percentage-based fee
    valid_data = {
        "fee_name": "Royalty Fee",
        "amount_percentage": 6.0,
        "frequency": "Monthly",
        "calculation_basis": "Gross Sales",
        "section_id": uuid4()
    }
    
    try:
        fee = OtherFee.model_validate(valid_data)
        print(f"✅ Valid OtherFee created: {fee.fee_name} - {fee.amount_percentage}%")
    except Exception as e:
        print(f"❌ OtherFee validation failed: {e}")
        return False
    
    return True

def test_outlet_summary_validation():
    """Test OutletSummary validation."""
    print("\n🧪 Testing OutletSummary validation...")
    
    # Valid data with correct math
    valid_data = {
        "fiscal_year": 2023,
        "outlet_type": "Franchised",
        "count_start": 100,
        "opened": 15,
        "closed": 5,
        "transferred_in": 2,
        "transferred_out": 3,
        "count_end": 109,  # 100 + 15 - 5 + 2 - 3 = 109
        "section_id": uuid4()
    }
    
    try:
        outlet = OutletSummary.model_validate(valid_data)
        print(f"✅ Valid OutletSummary created: FY{outlet.fiscal_year} - {outlet.count_end} outlets")
    except Exception as e:
        print(f"❌ OutletSummary validation failed: {e}")
        return False
    
    return True

def test_validation_config():
    """Test ValidationConfig constants."""
    print("\n🧪 Testing ValidationConfig...")
    
    print(f"✅ MAX_FEE_AMOUNT: ${ValidationConfig.MAX_FEE_AMOUNT/100:,.2f}")
    print(f"✅ MAX_ROYALTY_PERCENTAGE: {ValidationConfig.MAX_ROYALTY_PERCENTAGE}%")
    print(f"✅ MIN_SAMPLE_SIZE_FOR_FPR: {ValidationConfig.MIN_SAMPLE_SIZE_FOR_FPR}")
    
    return True

def main():
    """Run all validation tests."""
    print("🚀 Starting schema validation tests...")
    
    tests = [
        test_initial_fee_validation,
        test_other_fee_validation,
        test_outlet_summary_validation,
        test_validation_config
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)