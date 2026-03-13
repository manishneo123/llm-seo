import { Link } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/Card';

export function HowItWorks() {
  return (
    <div className="page dashboard">
      <header className="page-header">
        <h1 className="page-title">How TRUSEO works</h1>
        <p className="page-description">
          TRUSEO is an agentic loop that discovers what your site does, generates real buyer queries,
          monitors LLMs for visibility, and turns gaps into content actions.
        </p>
      </header>

      <Card className="trial-results-card">
        <CardHeader>
          <CardTitle>1. Discover your domain</CardTitle>
          <CardDescription>Use AI to build a structured profile for each site you care about.</CardDescription>
        </CardHeader>
        <CardContent>
          <p>
            Start by adding your domain (for example, <code>voicing.ai</code>). TRUSEO crawls key pages and uses
            LLMs to extract a rich profile:
          </p>
          <ul>
            <li>Primary category and up to three related categories</li>
            <li>Niche and value proposition</li>
            <li>Key topics and target audience</li>
            <li>Competitors and adjacent brands</li>
          </ul>
          <p>
            This profile becomes the shared context for prompt generation, monitoring, and brief creation.
          </p>
        </CardContent>
      </Card>

      <Card className="trial-results-card">
        <CardHeader>
          <CardTitle>2. Generate real buyer prompts</CardTitle>
          <CardDescription>Discovery-style queries users ask before they know your brand.</CardDescription>
        </CardHeader>
        <CardContent>
          <p>
            For each domain profile, TRUSEO asks LLMs to generate high-intent, discovery-style prompts. The system
            explicitly forbids using your brand or domain name in the prompt text and filters out anything that
            mentions it.
          </p>
          <p>
            The result is a canonical library of questions your ideal customers ask when they are exploring tools,
            not brands – perfect targets for monitoring and content.
          </p>
        </CardContent>
      </Card>

      <Card className="trial-results-card">
        <CardHeader>
          <CardTitle>3. Monitor LLMs across models</CardTitle>
          <CardDescription>See who gets cited and mentioned for every prompt and model.</CardDescription>
        </CardHeader>
        <CardContent>
          <p>
            TRUSEO runs monitoring jobs that send each prompt to your configured models (OpenAI, Anthropic,
            Perplexity, Gemini). For every prompt × model combination, it:
          </p>
          <ul>
            <li>Parses citations (who is linked or referenced as a source)</li>
            <li>Detects brand and domain mentions in the answer text</li>
            <li>Flags competitor-only answers where your brand does not appear</li>
            <li>Stores full responses for debugging and re-analysis</li>
          </ul>
          <p>
            Monitoring can run on a schedule or on demand, and results are stored per execution and per run so you
            can compare over time.
          </p>
        </CardContent>
      </Card>

      <Card className="trial-results-card">
        <CardHeader>
          <CardTitle>4. Explore visibility and gaps</CardTitle>
          <CardDescription>Dashboards and detail views for research and diagnosis.</CardDescription>
        </CardHeader>
        <CardContent>
          <p>TRUSEO gives you several levels of visibility for research:</p>
          <ul>
            <li>
              <strong>Dashboard</strong> – aggregate stats: prompts tracked, own citations, brand mentions,
              competitor-only answers, and latest runs.
            </li>
            <li>
              <strong>Trial results</strong> – a public view (at <code>/try</code>) that shows discovery, prompt
              visibility grids, and per-prompt details so anyone can see how a domain is performing.
            </li>
            <li>
              <strong>Prompt detail</strong> – a “Visibility across runs” table that shows execution IDs, models,
              cited / brand mentioned / competitor-only icons, other cited domains, and a one-click view of the
              exact LLM answer.
            </li>
          </ul>
          <p>
            This is where you can quickly answer questions like “Which prompts are we winning?”, “Where are
            competitors dominating?”, and “Which models are most favorable today?”.
          </p>
        </CardContent>
      </Card>

      <Card className="trial-results-card">
        <CardHeader>
          <CardTitle>5. Turn gaps into briefs and content</CardTitle>
          <CardDescription>From visibility gaps to concrete content work.</CardDescription>
        </CardHeader>
        <CardContent>
          <p>
            Using visibility data, TRUSEO can highlight gaps where competitors are cited but you are not, where
            citations go elsewhere even when you are mentioned, or where no brand is visible yet.
          </p>
          <p>
            Those gaps feed into content briefs and, optionally, AI-generated drafts. Briefs capture the target
            prompts, desired angle, headings, entities to mention, schema suggestions, and competitors to
            differentiate from.
          </p>
        </CardContent>
      </Card>

      <Card className="trial-results-card">
        <CardHeader>
          <CardTitle>6. Close the loop</CardTitle>
          <CardDescription>Measure uplift after content ships and iterate.</CardDescription>
        </CardHeader>
        <CardContent>
          <p>
            After you publish new or improved content, TRUSEO re-runs monitoring on the same prompts and compares
            before vs. after:
          </p>
          <ul>
            <li>Citation rate changes for your domain</li>
            <li>Shifts in brand mentions and competitor-only answers</li>
            <li>Which prompts improved, stayed flat, or regressed</li>
          </ul>
          <p>
            This closes the loop: discover → generate prompts → monitor → find gaps → brief → create content → re-monitor.
          </p>
          <p>
            You can experiment with TRUSEO immediately via the{' '}
            <Link to="/try" className="link-btn">
              Try it free
            </Link>{' '}
            page, then sign up to add your own domains and schedule monitoring.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

