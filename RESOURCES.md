# Staging e implantação remota: recursos

## Knowledge

- [GitHub Docs: Deploying with GitHub Actions](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)
  Explica ambientes de deployment, gatilhos, concorrência e aprovações. Use para entender como `staging` e `production` aparecem no fluxo do GitHub.
- [GitHub Docs: Managing environments for deployment](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
  Fonte para regras de proteção, branches autorizadas e secrets separados por ambiente.
- [GitHub Docs: Deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
  Referência técnica sobre revisores, restrições de branch e momento em que secrets ficam disponíveis.
- [Tailscale Docs: Tailscale SSH](https://tailscale.com/docs/features/tailscale-ssh)
  Explica como autorizar acesso SSH pela identidade da tailnet sem copiar uma chave privada entre computadores.
- [Tailscale Docs: Serve e identity headers](https://tailscale.com/docs/features/tailscale-serve)
  Documenta o proxy privado, os headers de identidade verificados e a exigência de manter o backend em loopback.

## Wisdom (Communities)

- [GitHub Community: Actions](https://github.com/orgs/community/discussions/categories/actions)
  Use para comparar soluções de deployment e investigar limitações encontradas em workflows reais.

## Implementação local

- [Contrato remoto](docs/remote-runtime-contract.md)
- [Reconciliação e recuperação](docs/reconciliation-and-recovery.md)
- [Skill reutilizável](.agents/skills/remote-vps-runtime/SKILL.md)
