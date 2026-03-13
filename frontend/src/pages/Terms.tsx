import { Link } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';

export function Terms() {
  return (
    <div className="page dashboard">
      <header className="page-header">
        <h1 className="page-title">Terms and Conditions</h1>
        <p className="page-description">
          These Terms and Conditions (&quot;Terms&quot;) govern your use of the TRUSEO application and related
          services. By accessing or using TRUSEO, you agree to be bound by these Terms.
        </p>
      </header>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>1. Service description</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            TRUSEO is an analytics and content-planning tool that helps you understand how large language models
            (such as ChatGPT, Perplexity, Claude, and Gemini) cite and mention your domains, and to turn visibility
            gaps into content briefs and drafts. The product includes:
          </p>
          <ul>
            <li>Domain discovery and profiling using web crawling and AI-powered summaries.</li>
            <li>Prompt generation and monitoring across multiple LLM providers.</li>
            <li>Dashboards, reports, and trial flows that visualize citations, brand mentions, and competitors.</li>
            <li>Optional content briefs, drafts, and distribution workflows.</li>
          </ul>
          <p>
            TRUSEO is provided as a self-service tool to support your research and decision-making. You are solely
            responsible for how you interpret and act on the insights it provides.
          </p>
        </CardContent>
      </Card>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>2. Trial usage</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            TRUSEO offers an unauthenticated trial flow where you can analyse a domain by entering a website URL on
            the <Link to="/try">Try it free</Link> page. Trial runs may be subject to rate limits, queue backpressure,
            and domain reachability checks. We reserve the right to:
          </p>
          <ul>
            <li>Refuse or throttle trial requests (for example, to prevent abuse or protect underlying LLM APIs).</li>
            <li>Reuse recent trial results for the same domain within a defined window (e.g. 7 days).</li>
            <li>Change, pause, or discontinue the trial experience at any time.</li>
          </ul>
          <p>
            Trial results are provided for evaluation only. They may be incomplete, out-of-date, or inaccurate, and
            must not be treated as legal, financial, or any other form of professional advice.
          </p>
        </CardContent>
      </Card>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>3. Accounts and authenticated features</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            Certain features (for example, managing domains, prompts, briefs, drafts, and settings) require you to
            sign in. You are responsible for:
          </p>
          <ul>
            <li>Maintaining the confidentiality of your account credentials and access tokens.</li>
            <li>Ensuring that the domains and content you add belong to you or that you have permission to use them.</li>
            <li>Ensuring that your use of TRUSEO complies with all applicable laws and the terms of any third-party services you connect.</li>
          </ul>
          <p>
            We may suspend or terminate accounts that appear to be compromised, abusive, or in violation of these Terms.
          </p>
        </CardContent>
      </Card>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>4. Third-party APIs and providers</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            TRUSEO integrates with external APIs and providers (for example, OpenAI, Anthropic, Perplexity, Google
            Gemini, analytics tools such as Google Analytics, and optional CMS or distribution channels). Your use
            of those services is subject to their own terms and policies. You are responsible for:
          </p>
          <ul>
            <li>Supplying valid API keys and configuration in accordance with the provider&apos;s terms.</li>
            <li>Staying within the provider&apos;s rate limits, content policies, and acceptable use guidelines.</li>
            <li>Any charges, limits, or data processing performed by those third parties.</li>
          </ul>
          <p>
            We do not control or guarantee the availability, accuracy, or behaviour of any third-party service. If
            a provider changes or discontinues its API, parts of TRUSEO may degrade or stop working.
          </p>
        </CardContent>
      </Card>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>5. Data, privacy, and analytics</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            TRUSEO processes data such as domains you add, prompts, monitoring runs, citations, and aggregated
            statistics used for learning and improving the product (for example, citation uplift and brand-mention
            uplift). Where enabled, analytics tools such as Google Analytics may collect usage data about how you
            interact with the web application.
          </p>
          <p>
            You must not upload or input any personal data or sensitive information that you are not legally
            permitted to process. You are responsible for complying with any data-protection or privacy obligations
            applicable to your use of TRUSEO. For more information about how we handle data, please refer to our
            separate privacy policy (if provided).
          </p>
        </CardContent>
      </Card>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>6. Intellectual property</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            TRUSEO, including its UI, underlying code, workflows, and branding, is protected by intellectual property
            laws. You retain all rights to your own content, domains, prompts, briefs, and drafts, but grant us a
            limited licence to process that content as needed to operate the service (for example, to run monitoring
            and compute learning metrics).
          </p>
          <p>
            You must not reverse engineer, decompile, or attempt to extract source code from any part of TRUSEO
            except to the extent allowed by applicable law or the open-source licence for the codebase.
          </p>
        </CardContent>
      </Card>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>7. No guarantees and limitation of liability</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            TRUSEO is provided on an &quot;as is&quot; and &quot;as available&quot; basis. We do not guarantee that:
          </p>
          <ul>
            <li>Monitoring runs, trial results, or learning insights are complete, accurate, or error-free.</li>
            <li>LLM providers will return consistent or reproducible outputs over time.</li>
            <li>The service will be uninterrupted, secure, or free from bugs.</li>
          </ul>
          <p>
            To the maximum extent permitted by law, we are not liable for any indirect, incidental, special, or
            consequential damages, or for any loss of profits, revenue, or data arising from your use of TRUSEO or
            reliance on its outputs.
          </p>
        </CardContent>
      </Card>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>8. Acceptable use</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            You agree not to misuse TRUSEO, including (without limitation) by:
          </p>
          <ul>
            <li>Attempting to overload, attack, or bypass rate limits and queue protections.</li>
            <li>Using the trial or monitoring flows to target domains or brands you are not authorised to analyse.</li>
            <li>Uploading content that is illegal, abusive, or violates the rights of others.</li>
            <li>Using TRUSEO to build competing datasets or services in violation of applicable law or contracts.</li>
          </ul>
          <p>
            We reserve the right to suspend or block access where we reasonably believe there is abuse, security
            risk, or violation of these Terms.
          </p>
        </CardContent>
      </Card>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>9. Changes to the service and these Terms</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            We may update TRUSEO over time, including adding or removing features, changing integrations, or
            modifying limits. We may also update these Terms from time to time. When we make material changes, we
            will update the &quot;last updated&quot; date and may provide additional notice where appropriate.
          </p>
          <p>
            Your continued use of TRUSEO after changes take effect constitutes your acceptance of the updated Terms.
            If you do not agree to the updated Terms, you should stop using the service.
          </p>
        </CardContent>
      </Card>

      <Card className="card-ui">
        <CardHeader>
          <CardTitle>10. Contact</CardTitle>
        </CardHeader>
        <CardContent className="card-ui-content">
          <p>
            If you have questions about these Terms or about TRUSEO, please contact the project maintainers via the
            public repository linked in the header of this application.
          </p>
          <p>
            These Terms are provided for convenience as part of this application and do not constitute legal advice.
            If you require legally binding terms tailored to your organisation, please consult a qualified lawyer.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

