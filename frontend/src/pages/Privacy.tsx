export default function Privacy() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-white mb-8">Privacy Policy</h1>

      <div className="prose prose-invert max-w-none space-y-8">
        <p className="text-gray-300">
          Last updated: December 2024
        </p>

        <p className="text-gray-300">
          Clonnect ("we", "our", "us") is committed to protecting your privacy. This Privacy Policy
          explains how we collect, use, and protect your personal data in compliance with the
          General Data Protection Regulation (GDPR) and Spanish data protection laws.
        </p>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">1. Data We Collect</h2>
          <p className="text-gray-300 mb-4">We collect the following types of data:</p>
          <div className="space-y-4">
            <div>
              <h3 className="font-medium text-white">Account Data</h3>
              <p className="text-gray-400 text-sm">
                Email address, name, profile information provided during registration
              </p>
            </div>
            <div>
              <h3 className="font-medium text-white">Platform Connection Data</h3>
              <p className="text-gray-400 text-sm">
                Access tokens and IDs for connected platforms (Instagram, Telegram, WhatsApp)
              </p>
            </div>
            <div>
              <h3 className="font-medium text-white">Conversation Data</h3>
              <p className="text-gray-400 text-sm">
                Messages received and sent through your connected platforms
              </p>
            </div>
            <div>
              <h3 className="font-medium text-white">Configuration Data</h3>
              <p className="text-gray-400 text-sm">
                Personality settings, products, nurturing sequences you create
              </p>
            </div>
            <div>
              <h3 className="font-medium text-white">Analytics Data</h3>
              <p className="text-gray-400 text-sm">
                Message counts, lead scores, conversion metrics
              </p>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">2. How We Use Your Data</h2>
          <ul className="list-disc list-inside text-gray-300 space-y-2">
            <li>To provide and operate the AI DM response service</li>
            <li>To train and improve our AI models (anonymized)</li>
            <li>To generate analytics and insights for your dashboard</li>
            <li>To send service notifications and alerts</li>
            <li>To provide customer support</li>
            <li>To comply with legal obligations</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">3. Legal Basis for Processing</h2>
          <p className="text-gray-300">
            We process your data based on:
          </p>
          <ul className="list-disc list-inside text-gray-300 space-y-2 mt-2">
            <li><strong>Contract:</strong> To provide the services you requested</li>
            <li><strong>Legitimate Interest:</strong> To improve our services and prevent fraud</li>
            <li><strong>Consent:</strong> For optional features like marketing emails</li>
            <li><strong>Legal Obligation:</strong> To comply with applicable laws</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">4. Data Sharing</h2>
          <p className="text-gray-300">
            We do not sell your personal data. We may share data with:
          </p>
          <ul className="list-disc list-inside text-gray-300 space-y-2 mt-2">
            <li><strong>Service Providers:</strong> Infrastructure (Railway), AI providers (Groq/OpenAI)</li>
            <li><strong>Platform APIs:</strong> Meta (Instagram), Telegram, WhatsApp as required for functionality</li>
            <li><strong>Legal Authorities:</strong> When required by law or legal process</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">5. Data Retention</h2>
          <p className="text-gray-300">
            We retain your data for as long as your account is active. Conversation data older than
            90 days is automatically archived. Upon account deletion, all personal data is removed
            within 30 days, except where retention is required by law.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">6. Your Rights (GDPR)</h2>
          <p className="text-gray-300 mb-4">
            Under GDPR, you have the following rights:
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-gray-800/50 p-4 rounded-lg">
              <h3 className="font-medium text-white">Right to Access</h3>
              <p className="text-gray-400 text-sm">Request a copy of your personal data</p>
            </div>
            <div className="bg-gray-800/50 p-4 rounded-lg">
              <h3 className="font-medium text-white">Right to Rectification</h3>
              <p className="text-gray-400 text-sm">Correct inaccurate personal data</p>
            </div>
            <div className="bg-gray-800/50 p-4 rounded-lg">
              <h3 className="font-medium text-white">Right to Erasure</h3>
              <p className="text-gray-400 text-sm">Request deletion of your data</p>
            </div>
            <div className="bg-gray-800/50 p-4 rounded-lg">
              <h3 className="font-medium text-white">Right to Portability</h3>
              <p className="text-gray-400 text-sm">Receive your data in a portable format</p>
            </div>
            <div className="bg-gray-800/50 p-4 rounded-lg">
              <h3 className="font-medium text-white">Right to Object</h3>
              <p className="text-gray-400 text-sm">Object to processing based on legitimate interest</p>
            </div>
            <div className="bg-gray-800/50 p-4 rounded-lg">
              <h3 className="font-medium text-white">Right to Restrict</h3>
              <p className="text-gray-400 text-sm">Limit how we use your data</p>
            </div>
          </div>
          <p className="text-gray-300 mt-4">
            To exercise these rights, contact us at{" "}
            <a href="mailto:privacy@clonnect.com" className="text-cyan-400 hover:underline">
              privacy@clonnect.com
            </a>
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">7. Data Security</h2>
          <p className="text-gray-300">
            We implement appropriate security measures including:
          </p>
          <ul className="list-disc list-inside text-gray-300 space-y-2 mt-2">
            <li>Encryption of data in transit (TLS) and at rest</li>
            <li>Access controls and authentication</li>
            <li>Regular security assessments</li>
            <li>European data hosting (Railway EU)</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">8. Cookies</h2>
          <p className="text-gray-300">
            We use essential cookies for authentication and session management.
            We do not use tracking or advertising cookies. Third-party analytics
            (if enabled) are anonymized and comply with GDPR.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">9. International Transfers</h2>
          <p className="text-gray-300">
            Your data is primarily stored in the European Union. If data is transferred
            outside the EU (e.g., to AI providers), we ensure appropriate safeguards
            are in place (Standard Contractual Clauses).
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">10. Data Protection Officer</h2>
          <p className="text-gray-300">
            For privacy inquiries, contact our Data Protection Officer at{" "}
            <a href="mailto:dpo@clonnect.com" className="text-cyan-400 hover:underline">
              dpo@clonnect.com
            </a>
          </p>
          <p className="text-gray-300 mt-4">
            You also have the right to lodge a complaint with the Spanish Data Protection Agency
            (AEPD) at{" "}
            <a href="https://www.aepd.es" className="text-cyan-400 hover:underline" target="_blank" rel="noopener noreferrer">
              www.aepd.es
            </a>
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4">11. Changes to This Policy</h2>
          <p className="text-gray-300">
            We may update this Privacy Policy from time to time. We will notify you of
            significant changes by email or through the Service. Continued use after
            changes constitutes acceptance.
          </p>
        </section>
      </div>

      <div className="mt-12 flex gap-4 text-sm text-gray-500">
        <a href="/terms" className="hover:text-gray-300 transition-colors">Terms of Service</a>
        <span>•</span>
        <a href="/docs" className="hover:text-gray-300 transition-colors">Help & FAQ</a>
      </div>
    </div>
  );
}
