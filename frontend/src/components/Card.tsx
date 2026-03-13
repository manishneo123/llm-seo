/**
 * Card components – shadcn/ui-style layout and semantics.
 * Use with Card, CardHeader, CardTitle, CardDescription, CardContent.
 * Styled via App.css (no Tailwind).
 */

export function Card({ className = '', children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`card-ui ${className}`.trim()} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ className = '', children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`card-ui-header ${className}`.trim()} {...props}>
      {children}
    </div>
  );
}

export function CardTitle({ className = '', children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={`card-ui-title ${className}`.trim()} {...props}>
      {children}
    </h3>
  );
}

export function CardDescription({ className = '', children, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={`card-ui-description ${className}`.trim()} {...props}>
      {children}
    </p>
  );
}

export function CardContent({ className = '', children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`card-ui-content ${className}`.trim()} {...props}>
      {children}
    </div>
  );
}
