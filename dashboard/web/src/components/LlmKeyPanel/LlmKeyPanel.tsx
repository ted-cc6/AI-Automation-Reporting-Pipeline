import { Card } from "../common/Card";
import { Button } from "../common/Button";
import type { LlmValidateResponse, Provider } from "../../api/client";
import "./LlmKeyPanel.css";

const PROVIDER_LABELS: Record<Provider, string> = {
  gemini: "Gemini",
  anthropic: "Anthropic Claude",
  openai: "OpenAI",
};

export function LlmKeyPanel(props: {
  provider: Provider;
  onProviderChange: (p: Provider) => void;
  apiKey: string;
  onApiKeyChange: (v: string) => void;
  llmValidation: LlmValidateResponse | null;
  onValidateKey: () => void;
  validating: boolean;
  disabled: boolean;
  // When set, the provider choice is fixed and the picker row is hidden --
  // used by the Gender Study flow, whose pipeline only ever calls Claude.
  lockedProvider?: Provider;
}) {
  return (
    <Card
      title="Language model"
      subtitle="Used for dataset validation, qualitative tagging, and report writing. Your key stays in this browser session only."
    >
      {props.lockedProvider ? (
        <p className="locked-provider-note">This report always uses {PROVIDER_LABELS[props.lockedProvider]}.</p>
      ) : (
        <div className="provider-row">
          {(Object.keys(PROVIDER_LABELS) as Provider[]).map((p) => (
            <label key={p} className={`provider-choice ${props.provider === p ? "provider-choice--selected" : ""}`}>
              <input
                type="radio"
                name="provider"
                checked={props.provider === p}
                disabled={props.disabled}
                onChange={() => props.onProviderChange(p)}
              />
              {PROVIDER_LABELS[p]}
            </label>
          ))}
        </div>
      )}
      <div className="field-row">
        <label className="field field--grow">
          <span>API key</span>
          <input
            type="password"
            autoComplete="off"
            placeholder={`Paste your ${PROVIDER_LABELS[props.provider]} API key`}
            value={props.apiKey}
            disabled={props.disabled}
            onChange={(e) => props.onApiKeyChange(e.target.value)}
          />
        </label>
        <Button
          variant="secondary"
          disabled={props.disabled || !props.apiKey || props.validating}
          onClick={props.onValidateKey}
        >
          {props.validating ? "Checking…" : "Validate key"}
        </Button>
      </div>
      {props.llmValidation && (
        <p className={props.llmValidation.ok ? "field-success" : "field-error"}>
          {props.llmValidation.message}
        </p>
      )}
    </Card>
  );
}
