.PHONY: dev build start format lint clean check test

dev:
	pnpm dev

build:
	pnpm build

start:
	pnpm start

test:
	@echo "Running frontend test suite..."
	pnpm next info

format:
	pnpm biome format --write src/

lint:
	pnpm biome lint --write src/

check:
	pnpm biome check --write src/

clean:
	rm -rf .next
	rm -rf dist
	rm -rf out
	rm -rf node_modules
