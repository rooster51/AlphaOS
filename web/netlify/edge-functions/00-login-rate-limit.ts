type EdgeContext = {
  next(): Promise<Response>;
};

export default function loginRateLimit(_request: Request, context: EdgeContext) {
  return context.next();
}

export const config = {
  path: "/auth/login",
  rateLimit: {
    windowLimit: 5,
    windowSize: 60,
    aggregateBy: ["ip", "domain"],
  },
};
