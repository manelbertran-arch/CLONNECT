import { useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, Mail } from "lucide-react";

interface FAQ {
  q: string;
  a: string;
}

const faqs: FAQ[] = [
  {
    q: "How do I connect Instagram?",
    a: "Go to Settings > Connections > Instagram and follow the steps to connect your Instagram Business account. You'll need to authorize Clonnect through Meta's OAuth flow."
  },
  {
    q: "How do I connect Telegram?",
    a: "Go to Settings > Connections > Telegram. Create a bot with @BotFather on Telegram and paste the token. Your bot will automatically start responding to messages."
  },
  {
    q: "How do I connect WhatsApp?",
    a: "Go to Settings > Connections > WhatsApp. You'll need a WhatsApp Business API account through Meta. Follow the setup wizard to connect your business phone number."
  },
  {
    q: "How do I add products?",
    a: "Go to Settings > Products and click 'Add Product'. Fill in the name, price, description, and payment link. Your AI clone will recommend products based on conversation context."
  },
  {
    q: "How do I configure the bot's personality?",
    a: "Go to Settings > Personality. Describe how you speak, your tone, common phrases, and any emojis you frequently use. The more detail you provide, the more authentic your clone will sound."
  },
  {
    q: "How do I pause the bot?",
    a: "On the Dashboard, there's a 'Bot Online/Paused' toggle button. Click it to pause automatic responses. You can still view and manually respond to messages."
  },
  {
    q: "How much does Clonnect cost?",
    a: "During the beta, Clonnect is free. We'll announce pricing plans soon. Early beta users will receive special benefits."
  },
  {
    q: "Is my data secure?",
    a: "Yes. Your data is stored on European servers (Railway) and we comply with GDPR. You can export or delete your data at any time from Settings."
  },
  {
    q: "Does the bot respond 24/7?",
    a: "Yes, while the bot is active it responds automatically to all DMs, 24 hours a day, 7 days a week."
  },
  {
    q: "Can I see the conversations?",
    a: "Yes, in the Inbox section you can see all conversations and respond manually if needed. You can also see the AI's responses and the detected intent."
  },
  {
    q: "What happens if the bot doesn't know how to respond?",
    a: "If the bot detects a complex question or a high-value sales opportunity, it will notify you to respond personally. You can also set up escalation rules."
  },
  {
    q: "Can I customize the automatic responses?",
    a: "Yes! Go to Settings > Nurturing to customize follow-up sequences, or Settings > Personality to change how your clone communicates."
  },
  {
    q: "How does lead scoring work?",
    a: "The AI analyzes each conversation to detect purchase intent. Leads are scored from 0-100% and categorized as Cold, Warm, Hot, or Customer. High-intent leads trigger notifications."
  },
  {
    q: "Can I use Clonnect on multiple platforms?",
    a: "Yes! You can connect Instagram, Telegram, and WhatsApp simultaneously. All conversations are unified in one inbox."
  }
];

function FAQItem({ faq, isOpen, onToggle }: { faq: FAQ; isOpen: boolean; onToggle: () => void }) {
  return (
    <div className="border border-gray-700 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-4 text-left hover:bg-gray-800/50 transition-colors"
        onClick={onToggle}
      >
        <span className="font-medium text-white">{faq.q}</span>
        {isOpen ? (
          <ChevronUp className="w-5 h-5 text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-400 flex-shrink-0" />
        )}
      </button>
      {isOpen && (
        <div className="px-4 pb-4 text-gray-300">
          {faq.a}
        </div>
      )}
    </div>
  );
}

export default function Docs() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-white mb-2">Help & FAQ</h1>
      <p className="text-gray-400 mb-8">
        Find answers to common questions about using Clonnect
      </p>

      {/* Quick Links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <a
          href="/settings"
          className="flex items-center gap-3 p-4 bg-gray-800/50 hover:bg-gray-800 rounded-lg transition-colors"
        >
          <div className="w-10 h-10 bg-purple-600/20 rounded-lg flex items-center justify-center">
            <span className="text-xl">⚙️</span>
          </div>
          <div>
            <div className="font-medium text-white">Settings</div>
            <div className="text-sm text-gray-400">Configure your clone</div>
          </div>
        </a>
        <a
          href="/inbox"
          className="flex items-center gap-3 p-4 bg-gray-800/50 hover:bg-gray-800 rounded-lg transition-colors"
        >
          <div className="w-10 h-10 bg-cyan-600/20 rounded-lg flex items-center justify-center">
            <span className="text-xl">💬</span>
          </div>
          <div>
            <div className="font-medium text-white">Inbox</div>
            <div className="text-sm text-gray-400">View conversations</div>
          </div>
        </a>
        <a
          href="/leads"
          className="flex items-center gap-3 p-4 bg-gray-800/50 hover:bg-gray-800 rounded-lg transition-colors"
        >
          <div className="w-10 h-10 bg-green-600/20 rounded-lg flex items-center justify-center">
            <span className="text-xl">👥</span>
          </div>
          <div>
            <div className="font-medium text-white">Leads</div>
            <div className="text-sm text-gray-400">Manage your pipeline</div>
          </div>
        </a>
      </div>

      {/* FAQ */}
      <h2 className="text-xl font-semibold text-white mb-4">Frequently Asked Questions</h2>
      <div className="space-y-3">
        {faqs.map((faq, index) => (
          <FAQItem
            key={index}
            faq={faq}
            isOpen={openIndex === index}
            onToggle={() => setOpenIndex(openIndex === index ? null : index)}
          />
        ))}
      </div>

      {/* Contact Section */}
      <div className="mt-12 p-6 bg-gradient-to-r from-purple-900/30 to-indigo-900/30 rounded-xl border border-purple-500/30">
        <h3 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
          <Mail className="w-5 h-5" />
          Can't find what you're looking for?
        </h3>
        <p className="text-gray-300 mb-4">
          Our team is here to help. Reach out and we'll get back to you as soon as possible.
        </p>
        <a
          href="mailto:soporte@clonnect.com"
          className="inline-flex items-center gap-2 bg-purple-600 hover:bg-purple-500 text-white px-4 py-2 rounded-lg transition-colors"
        >
          Contact Support
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>

      {/* Links to Legal */}
      <div className="mt-8 flex gap-4 text-sm text-gray-500">
        <a href="/terms" className="hover:text-gray-300 transition-colors">Terms of Service</a>
        <span>•</span>
        <a href="/privacy" className="hover:text-gray-300 transition-colors">Privacy Policy</a>
      </div>
    </div>
  );
}
