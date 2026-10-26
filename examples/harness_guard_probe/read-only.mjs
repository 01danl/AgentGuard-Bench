// A manual validation overlay: expose only the production read tool.
export const name = 'agentguard-read-only-validation';
export const inject = ['tools'];
export function apply(ctx) {
  ctx.on('agent/created', ({ agent }) => {
    agent.ctx.tools.restrict({ allow: ['read'] });
  });
}
