"""
ResolveAI V2 — Master Unified Database Seeder
=============================================
Orchestrates initial database seeding across user accounts, baseline orders,
knowledge base policies, and multi-tenant demo scenarios.

Usage:
    python seed.py           # Seeds baseline users (Customer, Expert, Admin) and orders
    python seed.py --all     # Complete end-to-end seed (Users + Orders + Knowledge + Day 3 Demo)
    python seed.py --knowledge # Seeds Knowledge Base articles only
    python seed.py --demo    # Seeds Day 3 demo scenarios only
"""

import asyncio
import sys
import os
import argparse
from datetime import datetime, timezone
from sqlalchemy import select

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

from app.database import async_session_factory
import app.main  # Crucial: imports all models so relationships can resolve
from app.users.models import User
from app.experts.models import Expert
from app.commerce.models import Order
from app.auth.password import get_password_hash
from app.shared.models import UserRole

async def seed_base():
    """Seeds foundational users, expert profile, and baseline orders."""
    async with async_session_factory() as db:
        print("[SEED] Seeding baseline accounts and orders...")
        
        # 1. Demo Customer
        customer = await db.scalar(select(User).where(User.email == "customer@resolveai.com"))
        if not customer:
            customer = User(
                email="customer@resolveai.com",
                full_name="Demo Customer",
                password_hash=get_password_hash("password123"),
                role=UserRole.CUSTOMER,
                tenant_id="default",
                is_active=True,
            )
            db.add(customer)
            await db.flush()
            print("  Created Demo Customer (customer@resolveai.com / password123)")

        # 2. Demo Expert
        expert_user = await db.scalar(select(User).where(User.email == "expert@resolveai.com"))
        if not expert_user:
            expert_user = User(
                email="expert@resolveai.com",
                full_name="Demo Expert",
                password_hash=get_password_hash("password123"),
                role=UserRole.EXPERT,
                tenant_id="default",
                is_active=True,
            )
            db.add(expert_user)
            await db.flush()
            
            expert_profile = Expert(user_id=expert_user.id)
            db.add(expert_profile)
            print("  Created Demo Expert (expert@resolveai.com / password123)")

        # 3. Demo Admin
        admin_user = await db.scalar(select(User).where(User.email == "admin@resolveai.com"))
        if not admin_user:
            admin_user = User(
                email="admin@resolveai.com",
                full_name="Demo Admin",
                password_hash=get_password_hash("admin123"),
                role=UserRole.ADMIN,
                tenant_id="default",
                is_active=True,
            )
            db.add(admin_user)
            print("  Created Demo Admin (admin@resolveai.com / admin123)")

        # 4. Baseline Orders (Absorbed from seed_orders.py)
        ord_123 = await db.scalar(select(Order).where(Order.order_number == "ORD-123"))
        if not ord_123 and customer:
            ord_123 = Order(
                customer_id=customer.id,
                tenant_id="default",
                order_number="ORD-123",
                status="SHIPPED",
            )
            db.add(ord_123)
            print("  Created Order ORD-123 (SHIPPED)")

        ord_999 = await db.scalar(select(Order).where(Order.order_number == "ORD-999"))
        if not ord_999 and customer:
            ord_999 = Order(
                customer_id=customer.id,
                tenant_id="default",
                order_number="ORD-999",
                status="DELIVERED",
            )
            db.add(ord_999)
            print("  Created Order ORD-999 (DELIVERED)")

        await db.commit()
        print("[SEED] Baseline accounts and orders seeded successfully.")

async def run_all():
    """Runs complete end-to-end database seed."""
    await seed_base()
    
    # Run Knowledge Base seed
    try:
        from seed_knowledge import seed_knowledge
        await seed_knowledge()
    except Exception as e:
        print(f"[WARNING] Knowledge seeding encountered error: {e}")

    # Run Day 3 Demo seed
    try:
        from seed_day3 import seed_day3
        await seed_day3()
    except Exception as e:
        print(f"[WARNING] Day 3 demo seeding encountered error: {e}")
        
    print("\n[COMPLETE] Unified database seeding completed.")

def main():
    parser = argparse.ArgumentParser(description="ResolveAI Master Database Seeder")
    parser.add_argument("--all", action="store_true", help="Seed everything: Users, Orders, Knowledge, and Day 3 Demo.")
    parser.add_argument("--knowledge", action="store_true", help="Seed Knowledge Base articles only.")
    parser.add_argument("--demo", action="store_true", help="Seed Day 3 demo scenarios only.")
    
    args = parser.parse_args()
    
    if args.all:
        asyncio.run(run_all())
    elif args.knowledge:
        from seed_knowledge import seed_knowledge
        asyncio.run(seed_knowledge())
    elif args.demo:
        from seed_day3 import seed_day3
        asyncio.run(seed_day3())
    else:
        asyncio.run(seed_base())

if __name__ == "__main__":
    main()
