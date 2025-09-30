#!/usr/bin/env python3
"""
Payment Manager for Discord Bot
Provides functionality to send payment success messages via Discord DM.
"""

import discord
from datetime import datetime
from typing import Optional, Dict, Any
import asyncio

class PaymentManager:
    def __init__(self, bot):
        self.bot = bot
        self.db = None  # Database manager reference
        
    def set_database(self, db_manager):
        """Sets the database manager."""
        self.db = db_manager
    
    async def send_payment_success_dm(self, user_id: int, payment_data: Dict[str, Any]) -> bool:
        """
        Sends a DM to the user when payment is successful.
        
        Args:
            user_id (int): User Discord ID
            payment_data (dict): Payment information
                - product_name: Product name
                - amount: Payment amount
                - currency: Currency
                - transaction_id: Transaction ID
                - subscription_type: Subscription type (e.g., "Premium", "Starter")
                - duration: Subscription duration
                - features: Provided features
        
        Returns:
            bool: DM sending success status
        """
        try:
            # Get user object
            user = self.bot.get_user(user_id)
            if not user:
                print(f"❌ User not found: {user_id}")
                return False
            
            # Create or get DM channel
            try:
                dm_channel = await user.create_dm()
            except discord.Forbidden:
                print(f"❌ Cannot create DM for user {user_id} (DM disabled)")
                return False
            
            # Create payment success embed
            embed = self._create_payment_success_embed(payment_data)
            
            # Send DM
            await dm_channel.send(embed=embed)
            
            # Save payment record to database
            if self.db:
                await self._save_payment_record(user_id, payment_data)
            
            print(f"✅ Payment success DM sent: {user_id}")
            return True
            
        except Exception as e:
            print(f"❌ Payment success DM sending failed: {e}")
            return False
    
    def _create_payment_success_embed(self, payment_data: Dict[str, Any]) -> discord.Embed:
        """Creates a payment success embed."""
        
        # Basic information
        product_name = payment_data.get('product_name', 'Premium Subscription')
        amount = payment_data.get('amount', 0)
        currency = payment_data.get('currency', 'USD')
        subscription_type = payment_data.get('subscription_type', 'Premium')
        duration = payment_data.get('duration', '1 month')
        features = payment_data.get('features', [])
        
        # Create embed
        embed = discord.Embed(
            title="🎉 Welcome to Engage Premium!",
            description=f"**{subscription_type} Access Purchased**",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        # Add product information
        embed.add_field(
            name="📦 Product Details",
            value=f"**{product_name}**\n"
                  f"💰 Amount: ${amount} {currency}\n"
                  f"⏰ Duration: {duration}",
            inline=False
        )
        
        # Provided features
        if features:
            features_text = "\n".join([f"• {feature}" for feature in features])
            embed.add_field(
                name="✨ Premium Features",
                value=features_text,
                inline=False
            )
        
        # Additional information
        embed.add_field(
            name="📋 Next Steps",
            value="• Your premium access has been activated\n"
                  "• Please connect your Discord on Whop to receive role on Engage Discord Server\n"
                  "• Enjoy your premium experience!",
            inline=False
        )
        
        # Footer
        embed.set_footer(
            text="Thank you for choosing Engage Premium!",
            icon_url=self.bot.user.avatar.url if self.bot.user and self.bot.user.avatar else None
        )
        
        # Thumbnail (optional)
        embed.set_thumbnail(url="https://imagedelivery.net/ZQ-g2Ke3i84UnMdCSDAkmw/premium-icon/public")
        
        return embed
    
    async def _save_payment_record(self, user_id: int, payment_data: Dict[str, Any]):
        """Saves payment record to database."""
        try:
            if not self.db:
                return
            
            # Save payment record
            transaction_id = payment_data.get('transaction_id', f"txn_{user_id}_{int(datetime.now().timestamp())}")
            
            # Save payment record to database (actual implementation may vary based on database structure)
            # Example: self.db.add_payment_transaction(user_id, transaction_id, payment_data)
            
            print(f"✅ Payment record saved: {user_id} - {transaction_id}")
            
        except Exception as e:
            print(f"❌ Payment record saving failed: {e}")
    
    async def send_payment_failure_dm(self, user_id: int, error_message: str) -> bool:
        """Sends a DM to the user when payment fails."""
        try:
            user = self.bot.get_user(user_id)
            if not user:
                return False
            
            dm_channel = await user.create_dm()
            
            embed = discord.Embed(
                title="❌ Payment Failed",
                description="We encountered an issue processing your payment.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="Error Details",
                value=error_message,
                inline=False
            )
            
            embed.add_field(
                name="Need Help?",
                value="Please contact our support team for assistance.",
                inline=False
            )
            
            await dm_channel.send(embed=embed)
            return True
            
        except Exception as e:
            print(f"❌ Payment failure DM sending failed: {e}")
            return False
    
    async def send_subscription_expiry_warning(self, user_id: int, days_remaining: int) -> bool:
        """Sends a subscription expiry warning DM."""
        try:
            user = self.bot.get_user(user_id)
            if not user:
                return False
            
            dm_channel = await user.create_dm()
            
            embed = discord.Embed(
                title="⚠️ Subscription Expiring Soon",
                description=f"Your premium subscription will expire in {days_remaining} days.",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="Renew Now",
                value="Visit our website to renew your subscription and continue enjoying premium features.",
                inline=False
            )
            
            await dm_channel.send(embed=embed)
            return True
            
        except Exception as e:
            print(f"❌ Subscription expiry warning DM sending failed: {e}")
            return False

# Payment webhook handler class
class PaymentWebhookHandler:
    def __init__(self, payment_manager: PaymentManager):
        self.payment_manager = payment_manager
    
    async def handle_payment_webhook(self, webhook_data: Dict[str, Any]) -> bool:
        """
        Handles payment webhooks.
        
        Args:
            webhook_data: Webhook data
                - user_id: User Discord ID
                - status: Payment status (success, failed, cancelled)
                - payment_data: Payment information
        """
        try:
            user_id = webhook_data.get('user_id')
            status = webhook_data.get('status')
            payment_data = webhook_data.get('payment_data', {})
            
            if not user_id:
                print("❌ No user_id in webhook.")
                return False
            
            if status == 'success':
                return await self.payment_manager.send_payment_success_dm(user_id, payment_data)
            elif status == 'failed':
                error_message = webhook_data.get('error_message', 'Unknown error')
                return await self.payment_manager.send_payment_failure_dm(user_id, error_message)
            else:
                print(f"❌ Unknown payment status: {status}")
                return False
                
        except Exception as e:
            print(f"❌ Webhook processing failed: {e}")
            return False

# Example usage functions
async def example_payment_success(bot, user_id: int):
    """Payment success example"""
    payment_manager = PaymentManager(bot)
    
    payment_data = {
        'product_name': 'Engage Starter',
        'amount': 9.99,
        'currency': 'USD',
        'subscription_type': 'Starter',
        'duration': '1 month',
        'transaction_id': f'txn_{user_id}_{int(datetime.now().timestamp())}',
        'features': [
            'Unlimited messages',
            'Premium characters access',
            'Priority support',
            'Exclusive content'
        ]
    }
    
    success = await payment_manager.send_payment_success_dm(user_id, payment_data)
    return success

async def example_payment_failure(bot, user_id: int):
    """Payment failure example"""
    payment_manager = PaymentManager(bot)
    
    error_message = "Insufficient funds. Please check your payment method."
    success = await payment_manager.send_payment_failure_dm(user_id, error_message)
    return success
