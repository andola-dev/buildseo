"use client";

import { Plug } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CredentialList } from "@/features/credentials/components/credential-list";

/**
 * Third-party integration credentials (spec §32).
 *
 * The backend groups non-AI credentials by `provider_type`: SEARCH powers
 * publisher discovery, SEO_METRICS and WEBSITE_INTELLIGENCE feed qualification
 * scoring. Each list is separate so it is clear which capability a missing key
 * disables.
 */
export function IntegrationSettings() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">Third-Party Integrations</h2>
        <p className="text-muted-foreground text-sm">
          Keys for the services that power discovery and publisher scoring. Stored
          encrypted and used only by the backend.
        </p>
      </div>

      <CredentialList
        providerType="SEARCH"
        providers={[]}
        title="Search providers"
        description="Used by publisher discovery to find candidate directories and listing sites."
        emptyDescription="Without a search provider, discovery can only use the built-in seed list."
      />

      <CredentialList
        providerType="SEO_METRICS"
        providers={[]}
        title="SEO metrics providers"
        description="Supply authority and organic traffic figures used in qualification scoring."
        emptyDescription="Without a metrics provider, authority and traffic stay unmeasured."
      />

      <CredentialList
        providerType="WEBSITE_INTELLIGENCE"
        providers={[]}
        title="Website intelligence providers"
        description="Enrich publisher records with additional site-level signals."
        emptyDescription="Optional. Adds extra signals to publisher qualification."
      />

      <Alert variant="info">
        <Plug aria-hidden />
        <AlertTitle>Which providers are available</AlertTitle>
        <AlertDescription>
          The set of supported integration providers is decided by the backend. Discovery
          providers that need a key are listed on the Discovery screen, and marked
          unavailable until one is configured here.
        </AlertDescription>
      </Alert>
    </div>
  );
}
